"""Validate artifacts and exercise each install outside the checkout, without Git.

Run with `uv run python scripts/check_release.py --output artifacts/install-check`.
Requires uv on PATH (or an installed uv Python module). Never reuses an output tree.
"""

import argparse
import email
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path

from packaging.requirements import Requirement

EXAMPLE_FILES = (
    "__init__.py",
    "order_app.py",
    "order_adapter.py",
    "test_existing_workflow.py",
)


def read_sdist_examples(sdist: Path) -> dict[str, bytes]:
    """Read only the four required regular members; never extract archive paths."""
    prefix = sdist.name.removesuffix(".tar.gz")
    examples = {}
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        for name in EXAMPLE_FILES:
            path = f"{prefix}/examples/{name}"
            matches = [member for member in members if member.name == path]
            if len(matches) != 1 or not matches[0].isfile():
                raise ValueError(f"sdist must contain exactly one regular file: {path}")
            file = archive.extractfile(matches[0])
            assert file is not None
            with file:
                examples[name] = file.read()
    return examples


def run(command, *, cwd, env=None, expected=0):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    assert result.returncode == expected, (command, result.returncode, expected)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    artifacts = sorted(p for p in (root / "dist").iterdir() if p.name.endswith((".whl", ".tar.gz")))
    sdists = [p for p in artifacts if p.name.endswith(".tar.gz")]
    wheels = [p for p in artifacts if p.suffix == ".whl"]
    assert len(sdists) == len(wheels) == 1, "dist must contain exactly one wheel and one sdist"
    shipped_examples = read_sdist_examples(sdists[0])
    uv = shutil.which("uv")
    uv_command = [uv] if uv else [sys.executable, "-m", "uv"]
    evidence = {"version": project["version"], "artifacts": []}
    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                names = archive.namelist()
                metadata = email.message_from_bytes(
                    archive.read(next(n for n in names if n.endswith("/METADATA")))
                )
                assert "fracture/py.typed" in names
                entrypoints = archive.read(
                    next(n for n in names if n.endswith("/entry_points.txt"))
                ).decode()
                assert "fracture = fracture.cli:app" in entrypoints
                assert "fracture/cli.py" in names
                assert not any(n.startswith(("tests/", "examples/")) for n in names)
        else:
            with tarfile.open(artifact) as archive:
                names = archive.getnames()
                member = archive.extractfile(next(n for n in names if n.endswith("/PKG-INFO")))
                assert member is not None
                metadata = email.message_from_bytes(member.read())
                for required in (
                    "src/fracture/py.typed",
                    "LICENSE",
                ):
                    assert any(n.endswith("/" + required) for n in names), required
        assert metadata["Name"] == project["name"]
        assert metadata["Version"] == project["version"]
        assert set(metadata["Requires-Python"].split(",")) == set(
            project["requires-python"].split(",")
        )
        assert {Requirement(r) for r in metadata.get_all("Requires-Dist")} == {
            Requirement(r) for r in project["dependencies"]
        }
        assert metadata["License-Expression"] == "MIT"
        started = time.monotonic()
        # Keep all campaign evidence in the requested tree; disposable environment is outside repo.
        with tempfile.TemporaryDirectory(prefix="fracture-release-") as temp:
            workspace = Path(temp)
            venv = workspace / "venv"
            run([*uv_command, "venv", str(venv), "--python", sys.executable], cwd=workspace)
            scripts = venv / ("Scripts" if os.name == "nt" else "bin")
            python = scripts / ("python.exe" if os.name == "nt" else "python")
            cli = scripts / ("fracture.exe" if os.name == "nt" else "fracture")
            run(
                [*uv_command, "pip", "install", "--python", str(python), str(artifact)],
                cwd=workspace,
            )
            requirements = run(
                [*uv_command, "pip", "freeze", "--python", str(python)], cwd=workspace
            )
            (output / f"{artifact.name}-runtime.txt").write_text(
                "\n".join(
                    line
                    for line in requirements.splitlines()
                    if not line.startswith("fracture-recovery")
                )
                + "\n"
            )
            example_package = workspace / "examples"
            example_package.mkdir()
            for name, content in shipped_examples.items():
                (example_package / name).write_bytes(content)
            env = {**os.environ, "PATH": str(scripts), "PYTHONPATH": str(workspace)}
            run(
                [
                    str(python),
                    "-c",
                    "import examples.order_app, sys; assert 'fracture' not in sys.modules",
                ],
                cwd=workspace,
                env=env,
            )
            run(
                [
                    str(python),
                    "-c",
                    "import fracture, shutil, importlib.util; "
                    "assert shutil.which('git') is None; "
                    "assert importlib.util.find_spec('pytest') is None; "
                    "assert importlib.util.find_spec('ruff') is None; "
                    "assert importlib.util.find_spec('mypy') is None; "
                    "assert 'site-packages' in fracture.__file__; "
                    "print(fracture.__file__)",
                ],
                cwd=workspace,
                env=env,
            )
            destination = output / artifact.name
            run(
                [
                    str(cli),
                    "test",
                    "examples.order_adapter:corrected",
                    "--output",
                    str(destination / "campaign"),
                ],
                cwd=workspace,
                env=env,
            )
            run(
                [
                    str(cli),
                    "replay",
                    str(destination / "campaign/replay.json"),
                    "--output",
                    str(destination / "replay"),
                ],
                cwd=workspace,
                env=env,
            )
            spec = json.loads((destination / "campaign/replay.json").read_text())
            assert spec["fingerprint"]["source_revision"] is None
            run(
                [
                    str(cli),
                    "test",
                    "missing_order_target:scenario",
                    "--output",
                    str(destination / "missing"),
                ],
                cwd=workspace,
                env=env,
                expected=2,
            )
            run(
                [
                    str(cli),
                    "test",
                    "examples.order_adapter:corrected",
                    "--output",
                    str(destination / "campaign"),
                ],
                cwd=workspace,
                env=env,
                expected=2,
            )
            changed = {**spec, "fingerprint": {**spec["fingerprint"], "dependencies": {}}}
            (destination / "incompatible.json").write_text(json.dumps(changed))
            run(
                [
                    str(cli),
                    "replay",
                    str(destination / "incompatible.json"),
                    "--output",
                    str(destination / "incompatible"),
                ],
                cwd=workspace,
                env=env,
                expected=2,
            )
            assert not (destination / "incompatible").exists()
            consumer = workspace / "consumer.py"
            consumer.write_text(
                "from fracture import Scenario, load_scenario\n"
                "scenario: Scenario = load_scenario('examples.order_adapter:corrected')\n"
            )
            typing_command = [
                *uv_command,
                "tool",
                "run",
                "mypy==1.20.2",
                "--python-executable",
                str(python),
                str(consumer),
            ]
            run(typing_command, cwd=workspace)
            consumer.write_text("from fracture import Scenario\nscenario: Scenario = 1\n")
            run(typing_command, cwd=workspace, expected=1)
            run(
                [
                    str(cli),
                    "test",
                    "examples.order_adapter:non_idempotent",
                    "--output",
                    str(destination / "negative"),
                ],
                cwd=workspace,
                env=env,
                expected=1,
            )
            run(
                [
                    str(cli),
                    "replay",
                    str(destination / "negative/replay.json"),
                    "--output",
                    str(destination / "negative-replay"),
                ],
                cwd=workspace,
                env=env,
                expected=1,
            )
            run(
                [*uv_command, "pip", "install", "--python", str(python), "pytest>=9,<10"],
                cwd=workspace,
            )
            run(
                [
                    str(python),
                    "-m",
                    "pytest",
                    "examples/test_existing_workflow.py",
                    "--basetemp",
                    str(workspace / "pytest-temp"),
                ],
                cwd=workspace,
                env=env,
            )
        evidence["artifacts"].append(
            {
                "name": artifact.name,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "seconds": round(time.monotonic() - started, 3),
                "result": "pass",
            }
        )
    (output / "build-evidence.json").write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
