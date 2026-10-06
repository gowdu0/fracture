"""Portable local replay specifications and compact evidence reports."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import platform
import subprocess
import unicodedata
from dataclasses import replace
from functools import partial
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .types import Budgets, CampaignReport, CaseReport, FaultCase, ReplaySpec, Scenario


def load_scenario(target: str) -> Scenario:
    module, separator, name = target.partition(":")
    if not separator or not module or not name:
        raise ValueError("scenario target must be module:attribute")
    try:
        value = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError) as error:
        raise ValueError(
            f"cannot load scenario {target!r}: {error}; install the target module and use "
            "an importable module:attribute (not a file path)"
        ) from error
    scenario = value() if callable(value) else value
    if not isinstance(scenario, Scenario):
        raise TypeError("scenario target must be a Scenario or a zero-argument Scenario factory")
    return replace(scenario, target=target)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fingerprint(scenario: Scenario) -> dict[str, Any]:
    package = Path(__file__).resolve().parent
    sources = {
        f"fracture/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.glob("*.py"))
    }
    objects: list[Any] = [
        scenario.workflow,
        type(scenario.backend),
        type(scenario.driver),
        *scenario.assertions,
    ]
    if scenario.target:
        objects.append(importlib.import_module(scenario.target.split(":")[0]))
    for value in objects:
        if isinstance(value, partial):
            value = value.func
        path = inspect.getsourcefile(value)
        if path:
            label = getattr(value, "__module__", getattr(value, "__name__", str(type(value))))
            sources[label] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    for index, path in enumerate(scenario.source_files):
        sources[f"explicit-{index}/{Path(path).name}"] = hashlib.sha256(
            Path(path).read_bytes()
        ).hexdigest()
    dependencies = {}
    for name in (
        "fracture-recovery",
        "langgraph",
        "langgraph-checkpoint",
        "langgraph-checkpoint-sqlite",
        "langchain-core",
        "langgraph-prebuilt",
        "langgraph-sdk",
        "pydantic",
        "aiosqlite",
        "ormsgpack",
        "langsmith",
    ):
        dependencies[name] = metadata.version(name)
    source_revision = None
    try:
        revision = subprocess.run(
            ["git", "-C", str(package), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if revision.returncode == 0:
            source_revision = revision.stdout.strip()
    except FileNotFoundError:
        pass  # Provenance is optional; compatibility hashes remain mandatory.
    return {
        "scenario": scenario.name,
        "version": scenario.version,
        "source_hashes": sources,
        "fixture_hash": digest(scenario.backend.describe()),
        "dependencies": dependencies,
        "python": platform.python_version(),
        "source_revision": source_revision,
        "checkpoint": {"backend": "sqlite", "durability": "sync", "async": scenario.asynchronous},
    }


def normalized(case: CaseReport) -> dict[str, Any]:
    return {
        "id": case.id,
        "validity": case.validity,
        "outcome": case.outcome,
        "reached": case.reached,
        "applied": case.applied,
        "invariants": [item.model_dump() for item in case.invariants],
        "placements": [
            {key: event[key] for key in ("boundary", "operation", "site", "occurrence", "attempt")}
            for event in case.events
            if event["kind"] == "boundary"
        ],
        "effects": case.final.get("effects", []),
        "result": case.result,
    }


def render_report(report: CampaignReport) -> str:
    lines = [f"Fracture: {report.scenario}"]
    for case in report.cases:
        status = "INVALID" if case.validity != "valid" else "PASS" if case.passed else "FAIL"
        lines.append(f"{status} {case.id}: outcome={case.outcome}, validity={case.validity}")
        if case.fault:
            f = case.fault
            lines.append(
                f"  Operation: {f.operation} / {f.site} / {f.occurrence}, attempt={f.attempt}"
            )
            lines.append(f"  Fault: {f.kind}; reached={case.reached}; applied={case.applied}")
        for item in case.invariants:
            if not item.passed:
                lines.append(f"  {item.name}: {item.detail}")
        if case.diagnostic:
            lines.append(f"  {case.diagnostic}")
        if any(p["injected_kill"] for p in case.processes):
            lines.append(f"  Processes: {case.processes}; thread={case.thread_id}")
    lines.extend(f"ERROR: {error}" for error in report.errors)
    lines.append(
        "Recovery cases (baseline reported separately): "
        + json.dumps(report.summary, sort_keys=True)
    )
    lines.append(f"Exit code: {report.exit_code}")
    if report.replay_path:
        lines.append(f'Replay: fracture replay "{report.replay_path}"')
    return "\n".join(lines) + "\n"


def terminal_text(value: Any, limit: int = 300) -> str:
    """Escape control/format characters and bound untrusted single-line labels."""
    text = str(value)
    escaped = "".join(
        f"\\u{ord(char):04x}"
        if unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        else char
        for char in text
    )
    return escaped if len(escaped) <= limit else escaped[:limit] + "..."


def recovery_evidence(case: CaseReport) -> tuple[bool, bool, bool]:
    """Confirm kill, new worker, and saved checkpoint continuity from recorded evidence."""
    killed = [
        p
        for p in case.processes
        if p.get("injected_kill") is True
        and isinstance(p.get("pid"), int)
        and p["pid"] > 0
        and p.get("exit_code") not in (None, 0)
        and any(
            e.get("kind") == "worker_killed"
            and e.get("worker_pid") == p.get("pid")
            and e.get("exit_code") == p.get("exit_code")
            for e in case.events
        )
    ]
    restarted = [
        p
        for p in case.processes
        if p.get("resumed") is True
        and isinstance(p.get("pid"), int)
        and p["pid"] > 0
        and any(p.get("pid") != old.get("pid") for old in killed)
        and any(
            e.get("kind") == "worker_started"
            and e.get("pid") == p.get("pid")
            and e.get("resume") is True
            and e.get("thread_id") == case.thread_id
            for e in case.events
        )
    ]
    continuity = False
    for crash in case.events:
        if crash.get("kind") != "crash_checkpoint":
            continue
        config = crash.get("config")
        if not isinstance(config, dict):
            continue
        identity = config.get("configurable", {})
        if not isinstance(identity, dict) or not identity.get("checkpoint_id"):
            continue
        if identity.get("thread_id") != case.thread_id:
            continue
        continuity |= any(
            e.get("kind") == "checkpoint"
            and e.get("phase") == "before"
            and e.get("config") == config
            and any(e.get("pid") == p.get("pid") for p in restarted)
            for e in case.events
        )
    return bool(killed), bool(restarted), continuity


def _inspection_status(case: CaseReport) -> tuple[str, str]:
    """Classify recorded results using only evidence required for inspection."""
    if case.validity != "valid":
        return "INVALID", f"case validity is {case.validity}"
    if not case.invariants:
        return "INVALID", "missing assertion results"
    if case.fault and not (case.reached and case.applied):
        missing = "/".join(name for name in ("reached", "applied") if not getattr(case, name))
        return "INVALID", f"missing required fault evidence: {missing}"
    return ("PASS" if case.passed else "FAIL"), ""


def render_evidence(
    report: CampaignReport, *, case_id: str | None = None, artifact: str | Path | None = None
) -> str:
    """Compact projection only: no arbitrary snapshot, result, receipt or event payloads."""
    selected = report.cases if case_id is None else [c for c in report.cases if c.id == case_id]
    if case_id is not None and not selected:
        raise ValueError(f"unknown case: {terminal_text(case_id)}")
    lines = [f"Fracture evidence: {terminal_text(report.scenario)}"]
    baseline = next((c for c in report.cases if c.id == "baseline"), None)
    baseline_status = "unknown"
    if baseline:
        baseline_status = _inspection_status(baseline)[0]
    lines.append(f"Baseline: {baseline_status}")
    recovery = [c for c in report.cases if c.id != "baseline"]
    recovery_statuses = [_inspection_status(c)[0] for c in recovery]
    lines.append(
        f"Recovery: {recovery_statuses.count('PASS')}/{len(recovery)} passing; "
        f"{recovery_statuses.count('INVALID')} invalid"
    )
    for case in selected:
        status, reason = _inspection_status(case)
        lines.append(f"{status} {terminal_text(case.id)}: {case.outcome}; validity={case.validity}")
        if reason:
            lines.append(f"  Inspection: {reason}")
        if case.fault:
            fault = case.fault
            lines.append(
                f"  {terminal_text(fault.operation)} / {terminal_text(fault.site)} / "
                f"{terminal_text(fault.occurrence)}; target attempt={fault.attempt}; "
                f"reached={case.reached}, applied={case.applied}"
            )
        attempts = [e for e in case.events if e.get("kind") == "attempt"]
        identities = {
            tuple(terminal_text(e.get(k, "unknown")) for k in ("operation", "site", "occurrence"))
            for e in attempts
        }
        if not case.fault:
            for identity in sorted(identities):
                lines.append("  Operation/site/occurrence: " + " / ".join(identity))
        effects = case.final.get("effects")
        count = len(effects) if isinstance(effects, list) else "unknown"
        lines.append(
            f"  Action attempts={len(attempts) if attempts else 'unknown'}; "
            f"durable effects={count} (fixture snapshot total)"
        )
        if case.fault and case.fault.kind == "after_commit_process_exit":
            kill, restart, continuity = recovery_evidence(case)
            lines.append(
                "  Confirmed kill/restart/checkpoint continuity: "
                + "/".join("yes" if v else "unknown" for v in (kill, restart, continuity))
            )
        if not case.invariants:
            lines.append("  Assertions: unknown (no results recorded)")
        for item in case.invariants:
            if not item.passed:
                lines.append(
                    f"  Assertion {terminal_text(item.name)}: {terminal_text(item.detail)}"
                )
        if case.diagnostic:
            lines.append(f"  Diagnostic: {terminal_text(case.diagnostic)}")
    lines.extend(f"ERROR: {terminal_text(error)}" for error in report.errors)
    if artifact is not None:
        lines.append(f"Report: {terminal_text(artifact, 1000)}")
        lines.append(f"Timeline/case stores: {terminal_text(Path(artifact).parent, 1000)}")
    if report.replay_path:
        lines.append(f"Replay artifact: {terminal_text(report.replay_path, 1000)}")
    return "\n".join(lines) + "\n"


def read_report(path: Path) -> CampaignReport:
    """Validate a schema-v1 JSON artifact without loading any application source."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
    ):
        raise ValueError("expected explicit schema_version 1 campaign report")
    try:
        report = CampaignReport.model_validate(data, strict=True)
    except ValidationError as error:
        fields = [
            ".".join(str(part) for part in item["loc"]) + ": " + item["type"]
            for item in error.errors(include_input=False, include_url=False)
        ]
        raise ValueError("invalid report fields: " + "; ".join(fields[:3])) from error
    ids = [c.id for c in report.cases]
    if len(ids) != len(set(ids)) or ids.count("baseline") != 1:
        raise ValueError("report must contain unique case IDs and one baseline")
    return report


def inspection_exit_code(report: CampaignReport) -> int:
    """Missing assertion evidence is invalid for inspection; selection never hides failures."""
    statuses = [_inspection_status(case)[0] for case in report.cases]
    if report.errors or not statuses or "INVALID" in statuses:
        return 2
    return 1 if "FAIL" in statuses else 0


def write_artifacts(
    scenario: Scenario, output: Path, report: CampaignReport, planned: list[FaultCase]
) -> None:
    if scenario.target:
        try:
            spec = ReplaySpec(
                target=scenario.target,
                fingerprint=fingerprint(scenario),
                fixture=scenario.backend.describe(),
                configuration=report.configuration,
                cases=planned,
                expected=[normalized(case) for case in report.cases],
            )
            (output / "replay.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
            report.replay_path = str(output / "replay.json")
        except Exception as error:
            report.errors.append(
                f"replay specification could not be written: {type(error).__name__}: {error}"
            )
    timeline = []
    for case in report.cases:
        timeline.append(f"\nCASE {case.id} thread={case.thread_id}")
        timeline.extend(
            f"{event['seq']:04d} {json.dumps(event, sort_keys=True)}" for event in case.events
        )
    (output / "timeline.txt").write_text("\n".join(timeline), encoding="utf-8")
    (output / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (output / "report.txt").write_text(render_report(report), encoding="utf-8")


def replay(specification: str | Path, output: str | Path | None = None) -> CampaignReport:
    from .runner import run_campaign

    path = Path(specification).resolve()
    spec = ReplaySpec.model_validate_json(path.read_text(encoding="utf-8"))
    scenario = load_scenario(spec.target)
    config = spec.configuration
    scenario = replace(
        scenario,
        budgets=Budgets(**config["budgets"]),
        approvals=tuple(config["approvals"]),
        initial_input=config["initial_input"],
        asynchronous=config["asynchronous"],
        faults=tuple(config["faults"]),
        continue_failed_baseline=config["continue_failed_baseline"],
    )
    current = fingerprint(scenario)
    differences = [
        key
        for key in current
        if key != "source_revision" and current[key] != spec.fingerprint.get(key)
    ]
    if scenario.driver.describe() != config["driver"]:
        differences.append("recovery driver")
    if scenario.backend.describe() != spec.fixture:
        differences.append("fixture")
    if differences:
        raise ValueError("replay environment mismatch: " + ", ".join(differences))
    destination = Path(output) if output else path.parent / "replayed"
    report = run_campaign(scenario, destination, cases=spec.cases)
    if [normalized(case) for case in report.cases] != spec.expected:
        report.errors.append(
            "replay mismatch: normalized placement, evidence, or invariant outcomes changed"
        )
        write_artifacts(scenario, destination, report, spec.cases)
    return report
