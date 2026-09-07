"""Working pytest usage example; reuses our demo and is NOT independent validation."""

import pytest

from fracture.demo import approved_change
from fracture.testing import assert_campaign


@pytest.fixture
def scenario():
    return approved_change()


def test_existing_workflow_recovery(scenario, tmp_path):
    report = assert_campaign(scenario, tmp_path / "recovery")
    assert report.summary["passes"] == 9
