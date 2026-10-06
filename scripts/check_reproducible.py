"""Rebuild into a disposable directory and compare the release artifact bytes."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/reproducible.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    command = [uv] if uv else [sys.executable, "-m", "uv"]
    with tempfile.TemporaryDirectory(prefix="fracture-rebuild-") as temp:
        subprocess.run([*command, "build", "--out-dir", temp], cwd=root, check=True)
        hashes = {}
        for path in Path(temp).iterdir():
            if not path.name.endswith((".whl", ".tar.gz")):
                continue
            original = root / "dist" / path.name
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == hashlib.sha256(original.read_bytes()).hexdigest(), path.name
            hashes[path.name] = digest
        assert len(hashes) == 2
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as file:
        json.dump(hashes, file, indent=2)
    print("Wheel and sdist are byte-identical across two builds")


if __name__ == "__main__":
    main()
