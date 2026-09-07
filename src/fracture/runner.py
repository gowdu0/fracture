"""Parent controller, real worker processes, and bounded baseline-derived campaigns."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import pickle
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .instrumentation import RunContext, _context
from .journal import Journal
from .types import (
    CampaignReport,
    CaseReport,
    CheckContext,
    FaultCase,
    InfrastructureError,
    InvariantResult,
    Scenario,
)


def _worker(
    scenario: Scenario,
    directory: Path,
    thread_id: str,
    fault: FaultCase | None,
    pipe: Any,
    resume: bool,
) -> None:
    journal = Journal(directory / "controller.sqlite")
    context = RunContext(directory, scenario, journal, thread_id, fault, pipe)
    token = _context.set(context)
    try:
        journal.event("worker_started", resume=resume, thread_id=thread_id)
        if scenario.asynchronous:

            async def invoke() -> dict[str, Any]:
                async with AsyncSqliteSaver.from_conn_string(
                    str(directory / "checkpoints.sqlite")
                ) as cp:
                    graph = scenario.workflow(context, cp)
                    return await scenario.driver.arun(graph, context, resume=resume)

            result = asyncio.run(invoke())
        else:
            with SqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as cp:
                graph = scenario.workflow(context, cp)
                result = scenario.driver.run(graph, context, resume=resume)
        pipe.send({"kind": "result", **result})
    except BaseException as error:
        journal.event("worker_error", type=type(error).__name__, message=str(error))
        pipe.send({"kind": "infrastructure_error", "message": f"{type(error).__name__}: {error}"})
    finally:
        _context.reset(token)
        pipe.close()


def _evaluate(scenario: Scenario, report: CaseReport) -> None:
    context = CheckContext(
        report.initial, report.final, report.outcome, report.result, report.events
    )
    for assertion in scenario.assertions:
        name = getattr(assertion, "__name__", type(assertion).__name__)
        try:
            result = assertion(context)
            if isinstance(result, InvariantResult):
                report.invariants.append(result)
            elif result is None:
                report.invariants.append(InvariantResult(name=name, passed=True))
            else:
                raise TypeError("custom assertions must return None or InvariantResult")
        except AssertionError as error:
            report.invariants.append(InvariantResult(name=name, passed=False, detail=str(error)))
        except Exception as error:
            report.validity = "infrastructure-error"
            report.diagnostic += f" assertion {name} errored: {type(error).__name__}: {error}"


def run_case(scenario: Scenario, directory: Path, fault: FaultCase | None = None) -> CaseReport:
    directory.mkdir(parents=True, exist_ok=False)
    report = CaseReport(
        id="baseline" if fault is None else fault.id,
        fault=fault,
        thread_id=f"fracture-{uuid.uuid4()}",
    )
    journal = Journal(directory / "controller.sqlite")
    journal.initialize()
    try:
        scenario.backend.prepare(directory)
        report.initial = scenario.backend.inspect(directory)
        if fault and not scenario.backend.supports(fault.site, fault.kind):
            report.validity = "unsupported"
            report.diagnostic = f"backend does not support {fault.kind} at {fault.site}"
        else:
            # Assertions run in the parent, so normal local pytest assertion closures are supported.
            worker_scenario = replace(scenario, assertions=())
            pickle.dumps(worker_scenario)
            ctx = mp.get_context("spawn")
            deadline = time.monotonic() + scenario.budgets.seconds
            restarts = 0
            resume = False
            while True:
                parent, child = ctx.Pipe()
                process = ctx.Process(
                    target=_worker,
                    args=(worker_scenario, directory, report.thread_id, fault, child, resume),
                    name="fracture-worker",
                )
                killed = False
                try:
                    process.start()
                    child.close()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not parent.poll(remaining):
                        raise InfrastructureError(
                            "case watchdog expired before worker result/barrier"
                        )
                    try:
                        message = parent.recv()
                    except EOFError as error:
                        raise InfrastructureError(
                            "worker exited without a result or acknowledged barrier"
                        ) from error
                    if message["kind"] == "commit_barrier":
                        if not fault or fault.kind != "after_commit_process_exit":
                            raise InfrastructureError("unexpected worker commit barrier")
                        if not scenario.backend.verify_commit(directory, message["receipt"]):
                            raise InfrastructureError("controller could not verify durable commit")
                        with SqliteSaver.from_conn_string(
                            str(directory / "checkpoints.sqlite")
                        ) as cp:
                            checkpoint = cp.get_tuple(
                                {"configurable": {"thread_id": report.thread_id}}
                            )
                            if checkpoint is None:
                                raise InfrastructureError(
                                    "no durable prior checkpoint at crash barrier"
                                )
                            journal.event(
                                "crash_checkpoint",
                                config=checkpoint.config,
                                metadata=checkpoint.metadata,
                            )
                        journal.set("fault_consumed", True)
                        journal.event(
                            "kill_requested", worker_pid=process.pid, receipt=message["receipt"]
                        )
                        process.kill()
                        process.join(timeout=min(10, max(0.1, deadline - time.monotonic())))
                        if process.is_alive() or process.exitcode in (None, 0):
                            raise InfrastructureError("worker termination was not confirmed")
                        killed = True
                        journal.set("fault_applied", True)
                        journal.event(
                            "worker_killed", worker_pid=process.pid, exit_code=process.exitcode
                        )
                    elif message["kind"] == "result":
                        report.outcome = message["outcome"]
                        report.result = message["result"]
                        process.join(timeout=min(10, max(0.1, deadline - time.monotonic())))
                        if process.is_alive() or process.exitcode != 0:
                            raise InfrastructureError(
                                "worker did not exit cleanly after its result"
                            )
                    else:
                        raise InfrastructureError(message.get("message", "unknown worker message"))
                finally:
                    child.close()
                    if process.pid is not None:
                        if process.is_alive():
                            process.kill()
                            process.join(timeout=10)
                        report.processes.append(
                            {
                                "pid": process.pid,
                                "exit_code": process.exitcode,
                                "resumed": resume,
                                "injected_kill": killed,
                            }
                        )
                        if process.is_alive():
                            raise InfrastructureError("worker cleanup failed")
                        process.close()
                    parent.close()
                if not killed:
                    break
                if not scenario.driver.restart_on_process_exit:
                    report.outcome = "failed"
                    report.result = {"error": "application driver does not restart workers"}
                    break
                if restarts >= scenario.budgets.restarts:
                    report.outcome = "recovery-exhausted"
                    report.result = {"error": "worker restart budget exhausted"}
                    break
                restarts += 1
                resume = True
    except (ValueError, pickle.PicklingError, AttributeError) as error:
        report.validity = "configuration-error"
        report.diagnostic = f"{type(error).__name__}: {error}"
    except Exception as error:
        report.validity = "infrastructure-error"
        report.diagnostic = f"{type(error).__name__}: {error}"
    finally:
        report.reached = journal.get("fault_reached", False)
        report.applied = journal.get("fault_applied", False)
        report.events = journal.events()
        try:
            report.final = scenario.backend.inspect(directory)
            report.backend_diff = {
                key: {"before": report.initial.get(key), "after": value}
                for key, value in report.final.items()
                if report.initial.get(key) != value
            }
        except Exception as error:
            report.validity = "infrastructure-error"
            report.diagnostic += f" backend inspection failed: {error}"
        if fault and report.validity == "valid" and not (report.reached and report.applied):
            report.validity = "unreached"
            report.diagnostic = "planned fault was not reached and applied"
        if report.final:
            _evaluate(scenario, report)
        (directory / "case.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def enumerate_cases(scenario: Scenario, baseline: CaseReport) -> list[FaultCase]:
    cases: dict[str, FaultCase] = {}
    for event in baseline.events:
        if event["kind"] != "boundary" or event["boundary"] not in scenario.faults:
            continue
        case = FaultCase(
            kind=event["boundary"],
            operation=event["operation"],
            site=event["site"],
            occurrence=event["occurrence"],
            attempt=event["attempt"],
        )
        cases[case.id] = case
    return list(cases.values())


def run_campaign(
    scenario: Scenario, output: str | Path, *, cases: list[FaultCase] | None = None
) -> CampaignReport:
    from .reports import write_artifacts

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = CampaignReport(
        scenario=scenario.name,
        configuration={
            "driver": scenario.driver.describe(),
            "budgets": asdict(scenario.budgets),
            "approvals": list(scenario.approvals),
            "initial_input": scenario.initial_input,
            "asynchronous": scenario.asynchronous,
            "faults": list(scenario.faults),
            "continue_failed_baseline": scenario.continue_failed_baseline,
        },
    )
    planned: list[FaultCase] = []
    if not scenario.assertions:
        report.errors.append("at least one business assertion is required")
    elif not scenario.name:
        report.errors.append("scenario name is required")
    else:
        baseline = run_case(scenario, output / "baseline")
        report.cases.append(baseline)
        if baseline.validity == "valid" and (baseline.passed or scenario.continue_failed_baseline):
            planned = cases if cases is not None else enumerate_cases(scenario, baseline)
            if not planned:
                report.errors.append("empty recovery campaign: no fault cases selected/observed")
            elif len({c.id for c in planned}) != len(planned):
                report.errors.append("duplicate fault cases")
            elif len(planned) > scenario.budgets.cases:
                report.errors.append(
                    f"{len(planned)} cases exceed campaign budget {scenario.budgets.cases}"
                )
            else:
                for fault in planned:
                    report.cases.append(run_case(scenario, output / fault.id, fault))
    observations = report.cases[0].events if report.cases else []
    report.summary = {
        "boundaries_observed": sum(e["kind"] == "boundary" for e in observations),
        "eligible_cases": sum(scenario.backend.supports(c.site, c.kind) for c in planned),
        "planned_cases": len(planned),
        "executed_cases": sum(bool(c.processes) for c in report.cases[1:]),
        "passes": sum(c.passed for c in report.cases[1:]),
        "failures": sum(c.validity == "valid" and not c.passed for c in report.cases[1:]),
        "unsupported": sum(c.validity == "unsupported" for c in report.cases[1:]),
        "unreached": sum(c.validity == "unreached" for c in report.cases[1:]),
        "other_invalid": sum(
            c.validity in ("infrastructure-error", "configuration-error") for c in report.cases[1:]
        ),
    }
    write_artifacts(scenario, output, report, planned)
    return report


async def arun_campaign(
    scenario: Scenario, output: str | Path, *, cases: list[FaultCase] | None = None
) -> CampaignReport:
    """Run the blocking parent controller in a thread; async workflow runs in spawned workers."""
    return await asyncio.to_thread(
        run_campaign, replace(scenario, asynchronous=True), output, cases=cases
    )
