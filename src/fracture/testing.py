"""Ordinary pytest helper; no global plugin registration."""

from pathlib import Path

from .reports import render_report
from .runner import run_campaign
from .types import CampaignReport, Scenario


def assert_campaign(scenario: Scenario, output: str | Path) -> CampaignReport:
    report = run_campaign(scenario, output)
    assert report.exit_code == 0, render_report(report)
    return report
