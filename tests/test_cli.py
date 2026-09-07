"""CLI exit semantics are tested through the real installed module entrypoint."""

import subprocess
import sys


def test_cli_defect_and_configuration_exit_codes(tmp_path):
    failure = subprocess.run(
        [
            sys.executable,
            "-m",
            "fracture.cli",
            "test",
            "fracture.demo:approval_replay",
            "--output",
            str(tmp_path / "defect"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert failure.returncode == 1, failure.stdout + failure.stderr
    assert "actual 2" in failure.stdout
    invalid = subprocess.run(
        [
            sys.executable,
            "-m",
            "fracture.cli",
            "test",
            "not-a-target",
            "--output",
            str(tmp_path / "invalid"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert invalid.returncode == 2, invalid.stdout + invalid.stderr
