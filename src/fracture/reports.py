"""Portable local replay specifications and compact evidence reports."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import platform
import subprocess
from dataclasses import replace
from functools import partial
from importlib import metadata
from pathlib import Path
from typing import Any

from .types import Budgets, CampaignReport, CaseReport, FaultCase, ReplaySpec, Scenario


def load_scenario(target: str) -> Scenario:
    module, separator, name = target.partition(":")
    if not separator or not module or not name:
        raise ValueError("scenario target must be module:attribute")
    value = getattr(importlib.import_module(module), name)
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
    revision = subprocess.run(
        ["git", "-C", str(package), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "scenario": scenario.name,
        "version": scenario.version,
        "source_hashes": sources,
        "fixture_hash": digest(scenario.backend.describe()),
        "dependencies": dependencies,
        "python": platform.python_version(),
        "source_revision": revision.stdout.strip() if revision.returncode == 0 else None,
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
