"""Synthetic integration; not independent adoption evidence."""

from fracture import replay, run_campaign
from fracture.testing import assert_campaign

from .demo_recovery import verify_orders
from .order_adapter import corrected, non_idempotent
from .order_app import build_workflow, prepare, ship


def test_application_without_fracture(tmp_path):
    path = tmp_path / "standalone.sqlite"
    prepare(path)
    graph = build_workflow(lambda op: ship(path, op))
    assert graph.invoke({"operation": "order-001"})["outcome"] == "completed"


def test_existing_workflow_recovery(tmp_path):
    report = assert_campaign(corrected(), tmp_path / "corrected")
    verify_orders(report, negative=False)
    assert report.summary["passes"] == 3
    crash = report.cases[-1]
    assert any(p["injected_kill"] for p in crash.processes)
    assert crash.processes[-1]["resumed"]
    assert any(e["kind"] == "crash_checkpoint" for e in crash.events)
    assert replay(report.replay_path, tmp_path / "replay").exit_code == 0


def test_non_idempotent_negative_control(tmp_path):
    report = run_campaign(non_idempotent(), tmp_path / "negative")
    verify_orders(report, negative=True)
    assert report.exit_code == 1
    assert report.cases[0].passed
    assert report.cases[1].passed
    assert all(not c.passed and c.validity == "valid" for c in report.cases[2:])
    assert replay(report.replay_path, tmp_path / "negative-replay").exit_code == 1
