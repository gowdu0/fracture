"""Capture real commands and pace an 84-second terminal recording; never overwrite evidence."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=84)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    commands = []
    with (args.output / "terminal.txt").open("x", encoding="utf-8") as capture:

        def emit(text):
            print(text, flush=True)
            capture.write(text + "\n")
            capture.flush()

        def run(arguments, expected=0):
            command = [sys.executable, *arguments]
            emit("$ python " + " ".join(str(a) for a in arguments))
            begin = time.perf_counter()
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            ) as process:
                assert process.stdout is not None
                for line in process.stdout:
                    emit(line.rstrip("\n"))
                code = process.wait()
            seconds = round(time.perf_counter() - begin, 3)
            commands.append({"arguments": arguments, "exit": code, "seconds": seconds})
            emit(f"[actual exit={code}; elapsed={seconds}s]")
            if code != expected:
                raise SystemExit(f"unexpected exit {code}; expected {expected}; capture retained")

        emit("Synthetic MIT order workflow: pytest evidence, durable writes, explicit recovery.")
        negative_test = args.output / "test_negative.py"
        negative_test.write_text(
            "from examples.order_adapter import non_idempotent\n"
            "from fracture.testing import assert_campaign\n\n"
            "def test_duplicate_shipment(tmp_path):\n"
            "    assert_campaign(non_idempotent(), tmp_path / 'campaign')\n",
            encoding="utf-8",
        )
        run(
            [
                "-m",
                "pytest",
                str(negative_test),
                "--tb=short",
                "-q",
                "--basetemp",
                str(args.output / "pytest-temp"),
            ],
            expected=1,
        )
        demo = args.output / "demo"
        run(["-m", "examples.demo_recovery", "--output", str(demo)])
        for name, expected in (("negative", 1), ("corrected", 0)):
            report = demo / name / "report.json"
            data = json.loads(report.read_text(encoding="utf-8"))
            crash = next(
                c["id"]
                for c in data["cases"]
                if c.get("fault") and c["fault"]["kind"] == "after_commit_process_exit"
            )
            run(["-m", "fracture.cli", "inspect", str(report), "--case", crash], expected)
        emit(
            "Two attempts can produce one durable effect. Inspect reads artifacts; replay executes."
        )
        emit("Independent integration remains outstanding. No production safety guarantee.")
        waiting = max(0, args.seconds - (time.perf_counter() - started))
        emit(f"[presentation hold={waiting:.3f}s; no execution waiting removed or sped up]")
        time.sleep(waiting)
        elapsed = round(time.perf_counter() - started, 3)
        emit(f"[recording elapsed={elapsed}s]")
    (args.output / "recording.json").write_text(
        json.dumps(
            {
                "commands": commands,
                "hold_seconds": round(waiting, 3),
                "elapsed_seconds": elapsed,
                "target_seconds": args.seconds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
