"""Synthetic, offline education: verify planted duplication, corrected recovery and replay."""

import argparse
import json
import time
from pathlib import Path

from fracture import replay, run_campaign
from fracture.reports import recovery_evidence, render_evidence
from fracture.types import FAULTS, CampaignReport

from .order_adapter import corrected, non_idempotent


def verify_orders(report: CampaignReport, *, negative: bool) -> None:
    """Check exact controls and durable state, not merely the campaign exit code."""
    if report.exit_code != (1 if negative else 0):
        raise AssertionError("unexpected campaign exit")
    if not (len(report.cases) == 4 and report.cases[0].id == "baseline"):
        raise AssertionError("unexpected order evidence")
    if not report.cases[0].passed:
        raise AssertionError("baseline must pass")
    if {c.fault.kind for c in report.cases[1:] if c.fault} != set(FAULTS):
        raise AssertionError("unexpected order evidence")
    for case in report.cases:
        if case.validity != "valid":
            raise AssertionError(case.diagnostic)
        post_commit = case.fault is not None and case.fault.kind != "before_action"
        expected_effects = 2 if negative and post_commit else 1
        effects = case.final.get("effects")
        if not (isinstance(effects, list) and len(effects) == expected_effects):
            raise AssertionError("unexpected order evidence")
        if not all(e["operation"] == "order-001" and e["action"] == "ship" for e in effects):
            raise AssertionError("unexpected order evidence")
        if case.passed != (expected_effects == 1):
            raise AssertionError("unexpected assertion outcome")
        if expected_effects == 2:
            if not any(
                i.name == "effect_count:order-001/ship" and not i.passed for i in case.invariants
            ):
                raise AssertionError("missing duplicate-effect assertion")
            if not all(
                i.passed for i in case.invariants if i.name != "effect_count:order-001/ship"
            ):
                raise AssertionError("unexpected order evidence")
        if case.fault:
            if not (case.reached and case.applied):
                raise AssertionError("unexpected order evidence")
        if case.fault and case.fault.kind == "after_commit_process_exit":
            if recovery_evidence(case) != (True, True, True):
                raise AssertionError("unconfirmed crash recovery")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        args.output.mkdir(parents=True, exist_ok=False)
        for name, scenario, negative in (
            ("negative", non_idempotent(), True),
            ("corrected", corrected(), False),
        ):
            report = run_campaign(scenario, args.output / name)
            print(render_evidence(report, artifact=args.output / name / "report.json"), flush=True)
            verify_orders(report, negative=negative)
        if report.replay_path is None:
            raise AssertionError("unexpected order evidence")
        replayed = replay(report.replay_path, args.output / "corrected-replay")
        verify_orders(replayed, negative=False)
        print(
            "PASS corrected replay: all cases, durable effects and checkpoint continuation verified"
        )
        seconds = round(time.perf_counter() - started, 3)
        (args.output / "demo-validation.json").write_text(
            json.dumps({"synthetic": True, "verified": True, "seconds": seconds}, indent=2),
            encoding="utf-8",
        )
        print(f"PASS educational driver; elapsed={seconds}s; evidence={args.output.resolve()}")
    except (AssertionError, OSError, ValueError) as error:
        from fracture.reports import terminal_text

        print(f"FAIL educational driver: {terminal_text(error)}", flush=True)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
