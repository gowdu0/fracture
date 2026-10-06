"""Replay provenance is optional; compatibility and failure semantics are mandatory."""

import json

import pytest

from examples.order_adapter import corrected
from fracture import load_scenario, replay, run_campaign
from fracture.reports import fingerprint


def test_missing_git_campaign_replay_and_mismatch(monkeypatch, tmp_path):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("fracture.reports.subprocess.run", missing)
    assert fingerprint(corrected())["source_revision"] is None
    report = run_campaign(corrected(), tmp_path / "run")
    assert report.exit_code == 0
    assert replay(report.replay_path, tmp_path / "replay").exit_code == 0
    spec = json.loads((tmp_path / "run/replay.json").read_text())
    spec["fingerprint"]["source_hashes"] = {}
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="source_hashes"):
        replay(changed, tmp_path / "incompatible")
    assert not (tmp_path / "incompatible").exists()


@pytest.mark.parametrize("target", ["missing_fracture_target:scenario", "fracture:missing"])
def test_actionable_target_diagnostics(target):
    with pytest.raises(ValueError, match="importable module:attribute"):
        load_scenario(target)


def test_commit_verifier_rejects_forged_receipt(tmp_path):
    from examples.order_adapter import OrderFixture
    from examples.order_app import ship

    backend = OrderFixture()
    backend.prepare(tmp_path)
    receipt = ship(tmp_path / "business.sqlite", "order-001")
    assert backend.verify_commit(tmp_path, receipt)
    assert not backend.verify_commit(tmp_path, {**receipt, "operation": "another-order"})
    assert not backend.verify_commit(tmp_path, {**receipt, "effect_id": 99})


def test_spawn_diagnostic_is_invalid(tmp_path):
    from dataclasses import replace

    from fracture import run_case

    scenario = replace(corrected(), workflow=lambda context, cp: None)
    case = run_case(scenario, tmp_path / "unpicklable")
    assert case.validity == "configuration-error"
    assert "module-level" in case.diagnostic


def test_existing_output_preserves_evidence(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    evidence = destination / "evidence.txt"
    evidence.write_text("retain me")
    with pytest.raises(FileExistsError, match="choose a fresh directory"):
        run_campaign(corrected(), destination)
    assert evidence.read_text() == "retain me"


def test_fixture_contract_diagnostic(tmp_path):
    from dataclasses import replace

    from fracture import run_case

    class MissingMethods:
        def inspect(self, directory):
            return {}

    case = run_case(replace(corrected(), backend=MissingMethods()), tmp_path / "fixture")
    assert case.validity == "configuration-error"
    assert "callable prepare()" in case.diagnostic
