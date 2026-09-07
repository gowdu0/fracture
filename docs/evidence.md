# Validation evidence

Recorded 2026-09-07 on Windows, CPython 3.12.14.

## Observed local results

- Behavioral suite: **40 passed in 89.62 seconds** (`python -m pytest -q`).
- Working pytest integration example: **1 passed in 18.06 seconds**.
- Ruff check: **all checks passed**. Formatting: **22 files already formatted**.
- mypy: **no issues found in 11 source files**.
- uv built both sdist and wheel; the wheel was built from the sdist.
- The wheel installed into a fresh environment with its runtime dependencies.
- All **12 educational scenarios passed their detection/control expectations** from that wheel.
- Clean-wheel replay of the corrected campaign passed its baseline and all 9 fault cases.
- No LLM credentials or live model calls were used.

The initial public-API semantics spike passed 3 tests, including sync/async
approval and error continuation and a real process kill followed by fresh-worker recovery.

## Captured crash evidence

The following is from the clean-wheel corrected campaign; these are real observed PIDs.

| Action | Killed PID / exit | New PID / exit | Durable effects for action |
| --- | --- | --- | --- |
| create_ticket | 35296 / -15 | 9840 / 0 | 1 |
| update_account | 16612 / -15 | 11076 / 0 | 1 |
| add_note | 40460 / -15 | 5088 / 0 | 1 |

Ticket crash thread: `fracture-8f243279-7f88-4fab-9779-4965b9b181cb`.
Checkpoint before kill and upon recovery: `1f1ab133-baed-6db5-8001-42750f56d093`.
Pending nodes upon recovery: `['ticket']`.
The recorded fault was reached and applied once. The resumed attempt returned a deduplicated result.

## Reproduce

```console
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run fracture demo --output artifacts/demo
uv run fracture test fracture.demo:approved_change --output artifacts/run
uv run fracture replay artifacts/run/replay.json
```

[Full captured demonstration reports](demo-output.txt) contain the failed and corrected outputs.
Wheel runs record source content hashes; Git revision can be null when installed source is outside a Git checkout.

## Remote CI and independent validation

The [GitHub Actions workflow](https://github.com/gowdu0/fracture/actions) defines Windows/Linux
and Python 3.12/3.13 jobs. Local results above do not imply a remote job passed;
inspect the run for the committed revision. Remote results are reported separately in the implementation handoff.

Milestone 2 remains incomplete. See [candidate assessment](independent-integration.md).
