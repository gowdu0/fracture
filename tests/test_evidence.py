"""Evidence is an escaped projection; inspect does not execute saved application targets."""

import json

import pytest
from typer.testing import CliRunner

from fracture.cli import app
from fracture.reports import render_evidence
from fracture.types import CampaignReport, CaseReport, FaultCase, InvariantResult


def case(name="baseline", passed=True, **kwargs):
    return CaseReport(
        id=name,
        invariants=[
            InvariantResult(name="custom", passed=passed, detail="arbitrary expected 17 apples")
        ],
        **kwargs,
    )


def invoke(tmp_path, report, *args):
    path = tmp_path / "report.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["inspect", str(path), *args])
    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) == {path}
    return result


def test_baseline_failure_not_hidden_by_selection(tmp_path):
    report = CampaignReport(scenario="custom", cases=[case(passed=False), case("other")])
    result = invoke(tmp_path, report, "--case", "other")
    assert result.exit_code == 1
    assert "Baseline: FAIL" in result.output
    assert "PASS other" in result.output


def test_mixed_invalid_and_failed_has_exit_two(tmp_path):
    result = invoke(
        tmp_path,
        CampaignReport(
            scenario="mixed", cases=[case(passed=False), case("bad", validity="unreached")]
        ),
    )
    assert result.exit_code == 2
    assert "INVALID bad" in result.output


def test_custom_assertion_and_unknown_evidence(tmp_path):
    report = CampaignReport(
        scenario="custom",
        cases=[case(passed=False)],
        configuration={"target": "not_importable:never"},
    )
    result = invoke(tmp_path, report)
    assert result.exit_code == 1
    assert "arbitrary expected 17 apples" in result.output
    assert "Action attempts=unknown; durable effects=unknown" in result.output
    assert "17" not in result.output.split("durable effects=")[1].splitlines()[0]


def test_missing_assertions_are_unknown_and_invalid(tmp_path):
    result = invoke(tmp_path, CampaignReport(scenario="empty", cases=[CaseReport(id="baseline")]))
    assert result.exit_code == 2
    assert "Assertions: unknown" in result.output
    assert "Baseline: INVALID" in result.output
    assert "INVALID baseline" in result.output
    assert "Inspection: missing assertion results" in result.output


@pytest.mark.parametrize("reached,applied", [(False, False), (False, True), (True, False)])
def test_incomplete_fault_evidence_is_invalid(tmp_path, reached, applied):
    fault = case(
        "fault",
        fault=FaultCase(kind="before_action", operation="op", site="s", occurrence="o"),
        reached=reached,
        applied=applied,
    )
    assert fault.passed  # Campaign result semantics remain unchanged.
    report = CampaignReport(scenario="incomplete", cases=[case(), fault])
    assert report.exit_code == 0
    result = invoke(tmp_path, report)
    assert result.exit_code == 2
    assert "Baseline: PASS" in result.output
    assert "Recovery: 0/1 passing; 1 invalid" in result.output
    assert "INVALID fault" in result.output
    assert "PASS fault" not in result.output
    assert "Inspection: missing required fault evidence:" in result.output
    for name, recorded in (("reached", reached), ("applied", applied)):
        assert (
            name in result.output.split("missing required fault evidence: ")[1].splitlines()[0]
        ) == (not recorded)


def test_missing_recovery_assertions_and_selection(tmp_path):
    report = CampaignReport(
        scenario="incomplete", cases=[case(), case("good"), CaseReport(id="empty")]
    )
    text = render_evidence(report)
    assert "Baseline: PASS" in text
    assert "Recovery: 1/2 passing; 1 invalid" in text
    assert "INVALID empty" in text
    assert "Inspection: missing assertion results" in text
    result = invoke(tmp_path, report, "--case", "good")
    assert result.exit_code == 2
    assert "PASS good" in result.output
    assert "INVALID empty" not in result.output
    assert "Recovery: 1/2 passing; 1 invalid" in result.output


@pytest.mark.parametrize("passed,expected", [(True, 0), (False, 1)])
def test_complete_recorded_results_keep_exit_semantics(tmp_path, passed, expected):
    report = CampaignReport(scenario="complete", cases=[case(), case("recovery", passed=passed)])
    result = invoke(tmp_path, report)
    assert result.exit_code == expected
    assert f"Recovery: {int(passed)}/1 passing; 0 invalid" in result.output
    assert f"{'PASS' if passed else 'FAIL'} recovery" in result.output


def test_campaign_errors_take_precedence_over_assertion_failure(tmp_path):
    report = CampaignReport(scenario="error", cases=[case(passed=False)], errors=["campaign error"])
    assert invoke(tmp_path, report).exit_code == 2


@pytest.mark.parametrize(
    "data",
    ["not json", "{}", '{"schema_version":2}', '{"schema_version":1,"scenario":"x","cases":{}}'],
)
def test_malformed_reports(tmp_path, data):
    path = tmp_path / "report.json"
    path.write_text(data)
    result = CliRunner().invoke(app, ["inspect", str(path)])
    assert result.exit_code == 2
    assert "Inspection error" in result.output
    assert path.read_text() == data


def test_unknown_case(tmp_path):
    result = invoke(tmp_path, CampaignReport(scenario="ok", cases=[case()]), "--case", "missing")
    assert result.exit_code == 2
    assert "unknown case" in result.output


def test_terminal_controls_and_payloads(tmp_path):
    report = CampaignReport(
        scenario="evil\x1b[2J\r\n\u202e",
        cases=[
            case(
                passed=False,
                final={"effects": [], "secret": "DO_NOT_PRINT"},
                result={"password": "DO_NOT_PRINT"},
                diagnostic="oops\x07",
            )
        ],
    )
    result = invoke(tmp_path, report)
    assert result.exit_code == 1
    assert "\\u001b" in result.output and "\\u202e" in result.output
    assert "\x1b" not in result.output and "\x07" not in result.output
    assert "DO_NOT_PRINT" not in result.output


def test_inspect_does_not_import_or_replay(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("execution forbidden")

    monkeypatch.setattr("fracture.reports.load_scenario", forbidden)
    monkeypatch.setattr("fracture.cli.run_campaign", forbidden)
    monkeypatch.setattr("fracture.cli.replay_run", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("fracture.reports.importlib.import_module", forbidden)
    result = invoke(tmp_path, CampaignReport(scenario="missing.module:factory", cases=[case()]))
    assert result.exit_code == 0, result.output


def test_pytest_failure_uses_compact_evidence(tmp_path, monkeypatch):
    from fracture.testing import assert_campaign

    report = CampaignReport(scenario="custom", cases=[case(passed=False)])
    monkeypatch.setattr("fracture.testing.run_campaign", lambda *args: report)
    with pytest.raises(AssertionError, match="Assertion custom") as error:
        assert_campaign(None, tmp_path / "campaign")
    assert str(tmp_path / "campaign/report.json") in str(error.value)
    report.cases[0].invariants[0].passed = True
    assert assert_campaign(None, tmp_path) is report


def test_duplicate_ids_invalid(tmp_path):
    result = invoke(tmp_path, CampaignReport(scenario="duplicates", cases=[case(), case()]))
    assert result.exit_code == 2


def test_unknown_crash_evidence(tmp_path):
    report = CampaignReport(
        scenario="unknown",
        cases=[
            case(),
            case(
                "crash",
                reached=True,
                applied=True,
                fault=FaultCase(
                    kind="after_commit_process_exit", operation="op", site="s", occurrence="o"
                ),
            ),
        ],
    )
    assert "unknown/unknown/unknown" in render_evidence(report)
    result = invoke(tmp_path, report)
    assert result.exit_code == 0
    assert "PASS crash" in result.output


def test_missing_pid_is_not_confirmed_kill():
    from fracture.reports import recovery_evidence

    missing = case(
        processes=[{"injected_kill": True, "exit_code": 1}],
        events=[{"kind": "worker_killed", "exit_code": 1}],
    )
    assert recovery_evidence(missing) == (False, False, False)


def test_boolean_schema_version_is_invalid(tmp_path):
    path = tmp_path / "report.json"
    data = CampaignReport(scenario="bad", cases=[case()]).model_dump()
    data["schema_version"] = True
    path.write_text(json.dumps(data))
    assert CliRunner().invoke(app, ["inspect", str(path)]).exit_code == 2


def test_malformed_report_error_omits_payload(tmp_path):
    path = tmp_path / "report.json"
    data = CampaignReport(scenario="bad", cases=[case()]).model_dump()
    data["unexpected"] = {"password": "DO_NOT_PRINT"}
    path.write_text(json.dumps(data))
    result = CliRunner().invoke(app, ["inspect", str(path)])
    assert result.exit_code == 2
    assert "unexpected: extra_forbidden" in result.output
    assert "DO_NOT_PRINT" not in result.output
