# Validation evidence

## Adoption/release slice: 2026-10-05

Starting checkout verified at `ab2eab4571eabffb39b6b962b916aad46fa07c39`.
The supplied workspace was an empty Git repository; origin was fetched and a
`codex/adoption-release` branch created at that exact commit, without resetting user files.
No applicable AGENTS.md was found. New code remains reviewable as local changes.

Local environment: Windows, CPython **3.13.2**, uv **0.12.23**. The frozen environment
was recreated as `.venv-release` after Windows denied removal of a dependency's
license directory in `.venv`. The interrupted old demo is not acceptance evidence.
The default pytest temp root also denied access; fresh writable `--basetemp` paths
under the existing `artifacts/` parent were used. No permission bypass or deletion
of user files was performed.

- Frozen sync, Ruff check, formatting check and mypy passed (11 source files).
- Final behavioral suite: **47 passed in 103.78 seconds**, including sync/async,
  negative controls, replay compatibility, forged receipt rejection, missing Git,
  import diagnostics, spawn pickling, fixture contracts and evidence preservation.
- Replacement synthetic pytest example: **3 passed in 33.87 seconds**.
- Measured console campaigns: corrected **11.980 s / exit 0**, non-idempotent
  **11.548 s / exit 1**, corrected replay **10.761 s / exit 0**. These are observed
  wall times including spawn overhead, not performance guarantees.
- Corrected: baseline plus all three faults pass. Negative: baseline and before-action
  pass; committed-response loss and actual process termination yield two shipments
  and valid assertion failures. Replay preserves each control's exit semantics.
- One synthetic application file / **49 lines**, one adapter file / **83 lines**,
  one pytest file / **33 lines**, and a **1-line** package marker. Counts include
  blanks, comments and fixture/verification/policy code; no integration code is hidden.
  Covered scope: **1 write site, 3 fault boundaries**, two business assertions.
- Application hooks: a write callback, optional checkpointer argument and one node
  that delegates to the callback. Correctness also requires the application's atomic
  operation-ID deduplication. These hooks were authored into the synthetic app;
  changes to a separately authored application cannot be measured or claimed here.

Detailed generated evidence is kept locally under `artifacts/` (excluded from Git):
`integration-measurements.json`, measured campaign/replay directories,
`full-demo-final/demo.json`, `install-check-final-2/build-evidence.json`, `reproducible-final-2.json`
and `audit-final/*.json`. The release helpers record final artifact hashes and actual
install/audit results; do not infer results from workflow definitions alone. CI
now retains these artifacts plus wheel/sdist files for seven days.

The strengthened install check validates both artifacts, runtime dependency metadata,
MIT license, typing marker and packaged example sources. It exercises the actual console
script, corrected and negative campaigns/replays, exit-2 invalid inputs and fresh-output
preservation outside the repository with Git absent and no dev packages. Separate mypy
consumer checks test accepted and rejected Scenario assignments; pytest is installed
only after the runtime checks. Both locked and fresh resolver exports are audited as complete pinned transitive lists
with `--no-deps --disable-pip`. The resolver-based scan omitted packaging; a direct
scan includes it. The unpublished project itself is not in the advisory index.

Initial pip-audit 2.10.1 scan found **3 advisories** in locked urllib3 2.7.0:
PYSEC-2026-4175, PYSEC-2026-4176 and PYSEC-2026-4177. Upstream fixes are in 2.8.0:
[proxy TLS configuration](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77),
[Deflate streaming loop](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g),
[chunk-size memory buffering](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw).
The lock updates only urllib3's resolved version; distribution metadata adds
`urllib3>=2.8,<3` so consumers retain the security floor. LangGraph/checkpointer,
Pydantic and Python compatibility pins are unchanged. uv's lock revision advances
with the locally used tool; CI now uses that same uv version. Post-fix audit JSON is
retained for the locked export and each separately resolved artifact installation.
Advisory scans are time-dependent and not a security guarantee; service failures block
approval rather than being reported as clean scans.

The preserved Windows/Linux × Python 3.12/3.13 matrix has **not been executed remotely
for these local changes**. Only Windows/Python 3.13.2 was executed locally; Python
3.12 and Linux results remain pending remote CI. The baseline's passed matrix is
not evidence for this new slice. No tags, credentials, releases or publication were
created. Version stays 0.1.0; [release checklist](release-checklist.md) requires
explicit approval for publication and retains unresolved limits.

Genuine independent integration remains incomplete. The next milestone is a
licensed, separately authored workflow with existing durable writes; current
friction justified narrow diagnostics, not a generic adapter framework or a UI.

## Historical baseline evidence

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
