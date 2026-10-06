# Pytest evidence milestone validation — 2026-10-06

## Current inspection-status review correction

The inspection renderer and exit calculation now share one case-status calculation.
Non-valid cases, missing assertion results, and required faults without both
reached/applied evidence are INVALID. Recovery counts use that same status.
Invalid evidence or campaign errors take precedence (2), followed by valid assertion
failures (1), then fully valid success (0). Case selection affects display only.
Optional attempts, backend projections and checkpoint details remain unknown when
absent; they do not invalidate a recorded assertion result. Campaign model properties,
schemas, execution, replay and normal test/replay exits are unchanged.

New checks for this correction, on Windows CPython 3.13.2 with the existing frozen
development environment (no worker campaigns):

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-release'
py -m uv run ruff format src/fracture/reports.py tests/test_evidence.py
py -m uv run pytest tests/test_evidence.py --basetemp artifacts/inspection-status-review-1
py -m uv run ruff check .
py -m uv run ruff format --check .
py -m uv run mypy
git diff --check
$reviewNewFiles = git ls-files --others --exclude-standard
foreach ($reviewNewFile in $reviewNewFiles) {
    git diff --no-index --check -- /dev/null $reviewNewFile
}
```

Observed: formatter updated two files; focused evidence tests **24 passed in 1.03s**;
Ruff lint passed; format check passed for **37 files**; mypy passed for **11 source
files**. Tracked and untracked whitespace checks produced no whitespace errors.
Regressions cover each missing reached/applied combination, missing baseline and
recovery assertions, matching labels/counts, selected passing cases with invalid
evidence elsewhere, error precedence, valid failure/success, and optional unknown
crash details. The inspection fixtures require no workers and remain unmodified.

All demo captures, full-suite results, builds, byte comparisons, clean installs and
audits below are **historical, before this correction**, even where their original
output paths contain "final". The reports.py source change alters replay fingerprints:
those captures and artifacts do not validate the final source, and their replay
compatibility is not claimed. The terminal capture is retained verbatim as prior
evidence. Fresh build/byte comparison, clean wheel/sdist installation and remote
matrix checks remain pending. Full suites, demos, recordings and audits were not
repeated for this focused presentation/inspection correction. No new Linux or Python
3.12 coverage is claimed; publication remains unexecuted.

## Historical milestone environment and base

Starting commit: `70a330f3a2963b5178c79960436bb51a2f56f2cb`.
Branch: `codex/pytest-evidence-demo`; changes are uncommitted. The clean prior
checkout was on `d2383ae`, whose tree is identical to the specified merge commit.
Fetched and verified the requested commit before creating this branch. No local
user changes were present. No applicable repository/ancestor `AGENTS.md` was found.

Environment: Windows, CPython 3.13.2, uv 0.12.23, pytest 9.1.1.
PowerShell sets `$env:UV_PROJECT_ENVIRONMENT = '.venv-release'`; all commands below
use `py -m uv` in place of `uv`. Fresh output paths retain raw local evidence under
ignored `artifacts/`. No local Linux/Python 3.12 execution is claimed.
For the final clean-install retry, `$env:UV_LINK_MODE = 'copy'` avoids this machine's
cloud-file hardlink restriction without changing dependency resolution or checks.

The starting main commit's [four-job matrix](https://github.com/gowdu0/fracture/actions/runs/37396580726)
was independently checked: Windows/Linux × Python 3.12/3.13 all succeeded. Those
results apply to the starting commit, not these uncommitted changes. New remote CI
is pending explicit commit/push authorization.

## Historical demo and recording evidence (before correction)

| Fresh demo output | Driver-measured seconds | Outcome |
| --- | ---: | --- |
| `artifacts/evidence-demo-1` | 36.664 | verified |
| `artifacts/evidence-recording-1/demo` | 38.212 | verified |
| `artifacts/evidence-recording-final/demo` | 41.637 | verified |
| `artifacts/evidence-recording-reviewed/demo` | 71.488 | verified; competing campaigns |
| `artifacts/evidence-recording-isolated/demo` | 43.091 | verified; isolated final capture |
| `artifacts/evidence-recording-final-code/demo` | 39.433 | verified; final error projection included |

Commands: `uv run python -m examples.demo_recovery --output artifacts/evidence-demo-1`,
and `uv run python scripts/record_demo.py --output artifacts/evidence-recording-1`
and `... --output artifacts/evidence-recording-final`, `... --output artifacts/evidence-recording-reviewed`,
and `... --output artifacts/evidence-recording-isolated`, and
`... --output artifacts/evidence-recording-final-code`. The first recording was a
development capture before adding the real pytest failure segment. The final capture
includes it. These were fresh executions, not replayed terminal text.

All six drivers verified: negative baseline and before-action pass with one
shipment; both negative post-commit cases fail with two; corrected baseline, all
three faults and replay pass with one. Both crash campaigns verify recorded nonzero
worker exit, different resumed worker PID and the same thread/checkpoint configuration.
The replay also uses existing source/environment and normalized outcome checks.

Final-code recording measured **84.001 seconds**. Subprocess durations: intentional
pytest failure 18.304s (exit 1), real demo including corrected replay 41.918s (exit 0),
negative case inspection 2.307s (exit 1), corrected inspection 1.844s (exit 0).
An explicitly labeled **19.601s presentation hold** was added. No execution waiting
was removed or accelerated. Durations include process startup and capture overhead;
the driver duration above excludes that overhead. Some checks ran concurrently on
this machine; these measurements are not a performance guarantee. The earlier
`evidence-recording-final` capture was also 84.000s with 18.951s hold. The reviewed
attempt overran to **105.904s**, with zero hold, during competing full-suite execution.
That overrun was retained, not edited or represented as an 84-second recording.
The later isolated capture measured 84.000s with 14.954s hold. The final-code capture
is the deliverable, with no competing campaigns running, after the malformed-report
error projection was finalized. Earlier outputs are retained as development evidence.

The [tracked actual terminal capture](pytest-evidence-terminal.txt) replaces only
the absolute checkout prefix with `<checkout>`; line endings are normalized. No
results, waits or failure text were fabricated. Original `terminal.txt`,
`recording.json`, `demo-validation.json`, reports and stores remain under the ignored
final recording directory. Sharing raw captures requires a sensitive-data review.
The guide includes unposted drafts; no social posting or contact occurred.

Adapter effort: `examples/order_adapter.py` remains **83 physical lines**, including
six fixture methods. No timed independently authored integration was performed.
The app is still synthetic. Independent revision/license, effort, controls and
blockers remain the next validation milestone; UI is deferred.

## Historical checks and development failures (before correction)

Frozen sync passed (58 packages). Initial Ruff found long lines/import ordering;
formatting and import fixes resolved them. Initial focused run: 20 passed, one
test failed because its import blocker intercepted its own monkeypatch setup.
Reordered setup; 21 then passed. Final review added missing-PID and boolean-schema
regressions. An omitted `json` import made that development run fail; fixed the
import. Final focused run: **23 passed** with
`uv run pytest tests/test_evidence.py tests/test_release_artifacts.py --basetemp artifacts/evidence-focused-final-2`.
Error-path review subsequently found Pydantic could echo payload values on malformed
input. Replaced that error text with field names/types, added a regression and an
installed CLI check. Final focused command
`uv run pytest tests/test_evidence.py tests/test_release_artifacts.py --basetemp artifacts/evidence-focused-payload`
passed **24 tests in 1.30s**.
Mypy passed for 11 source files. Lint/format checks passed at that milestone state.

Full suite before the final payload-error guard:
`uv run pytest --basetemp artifacts/evidence-full-final` — **70 passed in 270.71s**.
An earlier full run passed 68 tests in 229.86s before the two final regressions
were collected. Final focused tests exercised the added guards. Both full runs
were successful; the second was warranted by those guards, not routine repetition.
Final stabilized suite:
`uv run pytest --basetemp artifacts/evidence-full-payload-final` — **71 passed in 248.90s**.

`uv run pytest examples/test_existing_workflow.py --basetemp artifacts/evidence-examples-1`
— **3 passed in 75.94s**. Both installed-artifact gates repeat these example tests
using the final shipped driver validator, which now uses explicit raises so
optimized Python cannot disable outcome validation. A standalone `python -O`
negative check also confirmed invalid evidence is rejected. Its first shell command
had a quoting SyntaxError; the corrected stdin script passed. No application failure
was hidden by that harness correction.

`uv run fracture demo --output artifacts/evidence-full-demo-1` — all 12 expected
support-demo scenarios passed. Its normal campaigns include expected failures;
the educational command itself returned 0.
`uv run fracture replay artifacts/evidence-full-demo-1/approved_change/replay.json --output artifacts/evidence-full-replay-1`
— passed, exit 0. These were observed for the pre-correction milestone, rather than
copied from the previous branch; they are now historical evidence.

Final packaging commands (raw results and exact hashes are retained in their named
output files rather than embedding self-referential sdist hashes in this document):

```console
uv build
uv run python scripts/check_reproducible.py --output artifacts/evidence-reproducible-final-3.json
uv run python scripts/check_release.py --output artifacts/evidence-install-final-3
uv run python scripts/audit_runtime.py --output artifacts/evidence-audit-final --install-evidence artifacts/evidence-install-final-3
```

`evidence-install-final-3/build-evidence.json` records wheel/sdist pass status,
SHA-256 and elapsed time; each `*-runtime.txt` records the resolved runtime only.
The gate runs outside the checkout with Git and development packages unavailable,
uses only five required regular example members from the built sdist, invokes real
console test/replay/inspect commands with exits 0/1/2, and validates consumer typing.
For inspection it additionally removes the example source from the import path and
checks `find_spec('examples') is None`. Pytest is installed separately afterwards.
Audit JSON covers the locked runtime and both clean-install runtimes using the
existing direct-requirement audit (`--no-deps --disable-pip`); urllib3's security floor
remains `>=2.8,<3`. The audit is a point-in-time advisory check, not a lasting guarantee.

An initial build/byte comparison passed before final documentation/capture updates.
The final build/byte comparison above includes those updates. Reproducibility
remains limited to successive local builds; no cross-machine equivalence is claimed.
The first final clean-install attempt (`artifacts/evidence-install-final`) failed
before executing Fracture: uv could not hardlink cached urllib3 into the fresh
temporary environment (Windows cloud-file error 396). Its log was retained.
The retry uses copy mode and a new output tree; no dependency floor, check or
security control was weakened. The documentation of this failure requires the
second final rebuild/byte comparison; the earlier comparison also passed.
That retry passed wheel and sdist gates (244.127s and 217.482s), including three
shipped pytest tests each. The final error projection and capture then warranted
the third final rebuild/byte comparison and new gate tree above. No support-demo
or dependency-audit repetitions were made for these renderer/error-path changes.

The final third-build gate passed wheel (267.587s) and sdist (182.798s), including
three shipped tests each and the installed malformed-payload guard. The audit
passed all three lists: 49 dependencies each, zero known vulnerabilities and zero
skips. Pip-audit emitted its existing recommendation to hash pinned requirements;
the direct-requirement strategy was preserved. These results predate this correction.

Final whitespace review removed one extra blank line added while copying the
terminal capture; the raw capture was untouched. This documentation update and
that copy correction warranted `uv build` and
`uv run python scripts/check_reproducible.py --output artifacts/evidence-reproducible-final-4.json`.
The final wheel is byte-identical to the third-build wheel tested above; final
sdist runtime source, build configuration, metadata and all five required example
members match the tested third-build sdist. The final comparison/inspection is
saved in `artifacts/evidence-final-verification-4.json`. The changed documentation
does not warrant repeating the runtime campaigns or audits. This distinction is
explicit: the third-build archive was installed directly; the fourth archive's
unchanged installable contents were verified by comparison and its wheel build.

The recording's pytest failure is an expected negative control, not a failed
release gate. Unknown/malformed evidence returns inspection exit 2; case display
selection never hides an invalid or failing required case. Inspect does not verify
artifact authenticity or rerun assertions. Existing test/replay exits and schema-v1
models remain unchanged. No dependency or publishing workflow was added.
