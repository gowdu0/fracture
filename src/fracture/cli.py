"""Small CLI. Expected educational detection has different semantics from test execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .reports import (
    inspection_exit_code,
    load_scenario,
    read_report,
    render_evidence,
    render_report,
    terminal_text,
)
from .reports import replay as replay_run
from .runner import run_campaign

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
console = Console()


@app.command("inspect")
def inspect_report(
    report_json: Path,
    case: Annotated[str | None, typer.Option("--case")] = None,
) -> None:
    """Read schema-v1 evidence only. Exit 0=pass, 1=assertions failed, 2=invalid/unknown."""
    try:
        report = read_report(report_json)
        text = render_evidence(report, case_id=case, artifact=report_json)
    except (OSError, ValueError) as error:
        typer.echo(f"Inspection error: {terminal_text(error)}")
        raise typer.Exit(2) from error
    typer.echo(text, nl=False)
    raise typer.Exit(inspection_exit_code(report))


@app.command()
def test(target: str, output: Annotated[Path, typer.Option()] = Path("artifacts/run")) -> None:
    """Run a normal campaign; assertion failures return 1 and invalid tests return 2."""
    try:
        report = run_campaign(load_scenario(target), output)
        console.print(render_report(report), markup=False, highlight=False)
    except Exception as error:
        console.print(f"Configuration/infrastructure error: {error}", markup=False)
        raise typer.Exit(2) from error
    raise typer.Exit(report.exit_code)


@app.command()
def replay(specification: Path, output: Annotated[Path | None, typer.Option()] = None) -> None:
    """Reconstruct a controlled fixture and check normalized replay outcomes."""
    try:
        report = replay_run(specification, output)
        console.print(render_report(report), markup=False, highlight=False)
    except Exception as error:
        console.print(f"Replay error: {error}", markup=False)
        raise typer.Exit(2) from error
    raise typer.Exit(report.exit_code)


@app.command()
def demo(output: Annotated[Path, typer.Option()] = Path("artifacts/demo")) -> None:
    """Offline education: succeed only when planted defects are detected and controls pass."""
    expectations = {
        "approval_replay": (1, "effect_count:change_request_001/create_ticket"),
        "split_only": (1, "effect_count:change_request_001/create_ticket"),
        "unauthorized": (1, "authorized_effect:update_account"),
        "mismatched_unauthorized": (1, "authorized_effect:update_account"),
        "false_success": (1, "structured_claim_matches_state"),
        "approved_change": (0, None),
        "rejected": (0, None),
        "wrong_customer": (0, None),
        "wrong_parameters": (0, None),
        "wrong_operation": (0, None),
        "safe_failure": (0, None),
        "async_change": (0, None),
    }
    results = []
    try:
        output.mkdir(parents=True, exist_ok=False)
        for name, (expected, invariant) in expectations.items():
            report = run_campaign(load_scenario(f"fracture.demo:{name}"), output / name)
            detected = invariant is None or any(
                i.name == invariant and not i.passed for c in report.cases for i in c.invariants
            )
            passed = report.exit_code == expected and detected
            results.append(
                {
                    "scenario": name,
                    "expected_exit": expected,
                    "actual_exit": report.exit_code,
                    "demonstration_passed": passed,
                }
            )
            console.print(
                f"{'PASS' if passed else 'FAIL'} demo {name}: campaign exit={report.exit_code}, "
                f"expected={expected}; cases={len(report.cases)}",
                markup=False,
            )
            if not passed:
                console.print(render_report(report), markup=False)
        (output / "demo.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    except Exception as error:
        console.print(f"Demo infrastructure error: {error}", markup=False)
        raise typer.Exit(2) from error
    console.print(f"Evidence: {output.resolve()}", markup=False)
    raise typer.Exit(0 if all(r["demonstration_passed"] for r in results) else 1)


if __name__ == "__main__":
    app()
