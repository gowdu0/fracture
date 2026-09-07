"""Behavioral tests of durable outcomes, real crashes, invalid cases, and recovery controls."""

import asyncio
import json
import multiprocessing as mp
import time
from dataclasses import replace

import pytest
from langgraph.graph import END, START, StateGraph

from fracture import Budgets, FaultCase, LangGraphDriver, arun_campaign, run_campaign, run_case
from fracture.assertions import (
    authorized_effect,
    backend_state,
    effect_count,
    structured_claim_matches_state,
    terminal_outcome,
)
from fracture.demo import (
    OPERATION,
    PARAMETERS,
    RESOURCE,
    SQLiteBackend,
    approval_replay,
    approved_change,
    async_change,
    false_success,
    mismatched_unauthorized,
    rejected,
    safe_failure,
    split_only,
    unauthorized,
    wrong_customer,
    wrong_operation,
    wrong_parameters,
)
from fracture.reports import normalized, replay
from fracture.types import CampaignReport, CheckContext, InvariantResult


def fault(kind="after_commit_response_lost", site="create_ticket", **kwargs):
    return FaultCase(kind=kind, operation=OPERATION, site=site, occurrence="primary", **kwargs)


@pytest.fixture(scope="module")
def corrected(tmp_path_factory):
    path = tmp_path_factory.mktemp("corrected") / "campaign"
    report = run_campaign(approved_change(), path)
    assert report.exit_code == 0, report.model_dump_json(indent=2)
    return report, path


def test_campaign_generation_and_isolation(corrected):
    report, _ = corrected
    assert report.summary["eligible_cases"] == report.summary["passes"] == 9
    assert len({c.thread_id for c in report.cases}) == 10
    for case in report.cases:
        assert case.initial["effects"] == []
        assert len(case.final["effects"]) == 3
        assert case.final["customer_plan"] == "pro"


def test_crashes_resume_prior_checkpoint_with_one_shot_consumption(corrected):
    report, path = corrected
    for case in report.cases:
        if not case.fault or case.fault.kind != "after_commit_process_exit":
            continue
        assert case.reached and case.applied
        assert len(case.processes) == 2
        old, new = case.processes
        assert old["pid"] != new["pid"]
        assert old["exit_code"] != 0 and old["injected_kill"]
        assert new["exit_code"] == 0 and new["resumed"]
        killed = [e for e in case.events if e["kind"] == "worker_killed"]
        assert len(killed) == 1
        crash_cp = next(e for e in case.events if e["kind"] == "crash_checkpoint")
        resume_cp = next(
            e
            for e in case.events
            if e["kind"] == "checkpoint" and e["pid"] == new["pid"] and e["phase"] == "before"
        )
        assert crash_cp["config"] == resume_cp["config"]
        assert resume_cp["next"]
        assert (path / case.id / "application.sqlite").exists()
        assert (path / case.id / "controller.sqlite").exists()


def test_retries_are_not_counted_as_duplicate_effects(corrected):
    report, _ = corrected
    for case in report.cases[1:]:
        attempts = [
            e for e in case.events if e["kind"] == "attempt" and e["site"] == case.fault.site
        ]
        effects = [e for e in case.final["effects"] if e["action"] == case.fault.site]
        assert len(attempts) == 2
        assert len(effects) == 1
        assert {a["operation"] for a in attempts} == {OPERATION}
        assert len({a["attempt_id"] for a in attempts}) == 2
        assert case.passed


def test_normal_approval_replay_fails_baseline_without_fault(tmp_path):
    report = run_campaign(approval_replay(), tmp_path / "replay-defect")
    assert report.exit_code == 1
    assert len(report.cases) == 1
    baseline = report.cases[0]
    assert baseline.fault is None and not baseline.applied
    assert len(baseline.final["tickets"]) == 2
    assert not next(i for i in baseline.invariants if "create_ticket" in i.name).passed


@pytest.mark.parametrize("kind", ["after_commit_response_lost", "after_commit_process_exit"])
def test_separate_node_is_insufficient_without_idempotency(tmp_path, kind):
    report = run_campaign(split_only(), tmp_path / kind, cases=[fault(kind)])
    assert report.cases[0].passed
    case = report.cases[1]
    assert case.validity == "valid" and case.applied
    assert len(case.final["tickets"]) == 2
    assert report.exit_code == 1


@pytest.mark.parametrize("factory", [rejected, wrong_customer, wrong_parameters, wrong_operation])
def test_nonmatching_approvals_never_authorize_updates(tmp_path, factory):
    case = run_case(factory(), tmp_path / factory.__name__)
    assert case.passed and case.outcome == "rejected"
    assert not [e for e in case.final["effects"] if e["action"] == "update_account"]


@pytest.mark.parametrize("factory", [unauthorized, mismatched_unauthorized])
def test_authorization_defects_are_detected(tmp_path, factory):
    case = run_case(factory(), tmp_path / factory.__name__)
    assert case.validity == "valid"
    assert not next(
        i for i in case.invariants if i.name == "authorized_effect:update_account"
    ).passed


def test_false_success_and_safe_failure(tmp_path):
    bad = run_case(false_success(), tmp_path / "bad")
    good = run_case(safe_failure(), tmp_path / "good")
    assert not next(i for i in bad.invariants if i.name == "structured_claim_matches_state").passed
    assert good.passed and good.outcome == "failed"
    assert good.result["message"] == "Account change failed."


def test_before_action_safe_failure_preserves_backend(tmp_path):
    scenario = replace(
        approved_change(),
        driver=LangGraphDriver(),
        target=None,
        assertions=(
            effect_count(OPERATION, "create_ticket", 0),
            backend_state({}, unchanged=("customers", "effects", "tickets")),
            terminal_outcome("failed"),
        ),
    )
    case = run_case(scenario, tmp_path / "before", fault("before_action"))
    assert case.passed and case.applied
    assert case.final == case.initial


def test_no_implicit_recovery_after_committed_timeout(tmp_path):
    scenario = replace(
        approved_change(),
        driver=LangGraphDriver(),
        target=None,
        assertions=(effect_count(OPERATION, "create_ticket", 1), terminal_outcome("failed")),
    )
    case = run_case(scenario, tmp_path / "no-retry", fault())
    assert case.passed and len(case.processes) == 1
    assert len(case.final["tickets"]) == 1
    assert len([e for e in case.events if e["kind"] == "attempt"]) == 1


def test_invalid_and_failed_cases_coexist_without_passing(tmp_path):
    scenario = split_only()
    report = run_campaign(scenario, tmp_path / "mixed", cases=[fault(), fault(attempt=99)])
    assert report.cases[1].validity == "valid" and not report.cases[1].passed
    assert report.cases[2].validity == "unreached" and not report.cases[2].passed
    assert report.exit_code == 2 and report.summary["unreached"] == 1


def test_unsupported_fault_does_not_degrade(tmp_path):
    scenario = replace(
        approved_change(), backend=SQLiteBackend(capabilities=("before_action",)), target=None
    )
    report = run_campaign(scenario, tmp_path / "unsupported", cases=[fault()])
    case = report.cases[1]
    assert case.validity == "unsupported" and not case.applied and not case.processes
    assert report.exit_code == 2


@pytest.mark.parametrize("budget", [Budgets(attempts=1), Budgets(restarts=0), Budgets(steps=1)])
def test_budgets_have_explicit_outcomes(tmp_path, budget):
    scenario = replace(
        approved_change(),
        budgets=budget,
        target=None,
        assertions=(terminal_outcome("recovery-exhausted"),),
    )
    kind = "after_commit_process_exit" if budget.restarts == 0 else "before_action"
    case = run_case(scenario, tmp_path / "budget", None if budget.steps == 1 else fault(kind))
    assert case.passed and case.outcome == "recovery-exhausted"


def sleepy_workflow(context, checkpointer):
    def node(state):
        time.sleep(30)
        return {"done": True}

    builder = StateGraph(dict).add_node("wait", node)
    builder.add_edge(START, "wait").add_edge("wait", END)
    return builder.compile(checkpointer=checkpointer)


def test_watchdog_kills_worker_and_reports_infrastructure_failure(tmp_path):
    previous = {p.pid for p in mp.active_children()}
    scenario = replace(
        approved_change(), workflow=sleepy_workflow, target=None, budgets=Budgets(seconds=1)
    )
    case = run_case(scenario, tmp_path / "watchdog")
    assert case.validity == "infrastructure-error"
    assert "watchdog" in case.diagnostic
    assert {p.pid for p in mp.active_children()} == previous
    assert all(p["exit_code"] is not None for p in case.processes)


def test_empty_and_oversized_campaigns_are_invalid(tmp_path):
    assert run_campaign(approved_change(), tmp_path / "empty", cases=[]).exit_code == 2
    report = run_campaign(replace(approved_change(), budgets=Budgets(cases=1)), tmp_path / "cap")
    assert report.exit_code == 2 and len(report.cases) == 1
    assert report.summary["planned_cases"] == 9
    assert CampaignReport(scenario="empty").exit_code == 2


def test_ordinary_python_assertions_and_assertion_errors(tmp_path):
    def assertion(context):
        assert context.final["customer_plan"] == "pro"

    scenario = replace(approved_change(), assertions=(assertion,), target=None)
    assert run_case(scenario, tmp_path / "custom").passed

    def broken(context):
        raise RuntimeError("checker bug")

    scenario.assertions = (broken,)
    assert run_case(scenario, tmp_path / "checker-bug").validity == "infrastructure-error"


def test_async_wrapper_and_async_campaign_entrypoint(tmp_path):
    report = asyncio.run(arun_campaign(async_change(), tmp_path / "async", cases=[fault()]))
    assert report.exit_code == 0
    assert report.cases[1].applied
    assert any(
        e["kind"] == "response_returned" and e["site"] == "create_ticket"
        for e in report.cases[1].events
    )


def test_replay_normalizes_process_ids_and_thread_ids(tmp_path):
    path = tmp_path / "original"
    original = run_campaign(approved_change(), path, cases=[fault("after_commit_process_exit")])
    replayed = replay(path / "replay.json", tmp_path / "replayed")
    assert original.exit_code == replayed.exit_code == 0
    assert original.cases[1].thread_id != replayed.cases[1].thread_id
    assert normalized(original.cases[1]) == normalized(replayed.cases[1])


@pytest.mark.parametrize("changed", ["source_hashes", "dependencies", "fixture_hash"])
def test_replay_rejects_environment_mismatches(corrected, tmp_path, changed):
    _, path = corrected
    spec = json.loads((path / "replay.json").read_text())
    spec["fingerprint"][changed] = "different"
    modified = tmp_path / "replay.json"
    modified.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match=changed):
        replay(modified)


def test_historical_authorization_and_current_operation_evidence():
    effect = {
        "id": 1,
        "operation": OPERATION,
        "action": "update_account",
        "resource": RESOURCE,
        "parameters": PARAMETERS,
        "sequence": 1,
    }
    approval = {
        "approved": True,
        "operation": OPERATION,
        "resource": RESOURCE,
        "parameters": PARAMETERS,
        "sequence": 2,
    }
    context = CheckContext({}, {"effects": [effect], "approvals": [approval]}, "completed", {}, [])
    assert not authorized_effect("update_account")(context).passed
    context.final = {"effects": [], "resources": {RESOURCE: PARAMETERS}}
    context.result = {"claims": [{**effect, "success": True}]}
    assert not structured_claim_matches_state()(context).passed


def test_exit_code_precedence():
    from fracture.types import CaseReport

    good = CaseReport(id="good", invariants=[InvariantResult(name="ok", passed=True)])
    bad = CaseReport(id="bad", invariants=[InvariantResult(name="bad", passed=False)])
    invalid = CaseReport(id="invalid", validity="unsupported")
    assert CampaignReport(scenario="s", cases=[good]).exit_code == 0
    assert CampaignReport(scenario="s", cases=[good, bad]).exit_code == 1
    assert CampaignReport(scenario="s", cases=[bad, invalid]).exit_code == 2
