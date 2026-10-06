"""Audit the locked export and each clean-install runtime; retain JSON on failure."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install-evidence", type=Path, default=Path("artifacts/install-check"))
    args = parser.parse_args()
    uv = shutil.which("uv")
    command = [uv] if uv else [sys.executable, "-m", "uv"]
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    locked = destination / "locked-runtime.txt"
    subprocess.run(
        [
            *command,
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--format",
            "requirements-txt",
            "--output-file",
            str(locked),
        ],
        check=True,
        capture_output=True,
    )
    requirements = [locked, *sorted(args.install_evidence.glob("*-runtime.txt"))]
    assert len(requirements) == 3, "run clean artifact checks first (artifacts/install-check)"
    failed = False
    for path in requirements:
        result = subprocess.run(
            [
                *command,
                "tool",
                "run",
                "pip-audit==2.10.1",
                "--no-deps",
                "--disable-pip",
                "-r",
                str(path),
                "--format",
                "json",
                "--output",
                str(destination / (path.stem + ".json")),
            ]
        )
        failed |= result.returncode != 0
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
