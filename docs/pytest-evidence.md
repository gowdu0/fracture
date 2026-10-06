# Pytest evidence and order recording

This is a repository-authored, MIT-licensed synthetic order workflow. It is an
executable teaching example, not independent adoption or a production guarantee.
No package publication or social posting is part of this milestone.

## Install to pytest

Use Python 3.12 or 3.13. From this reviewed checkout:

```console
uv sync --frozen
uv build
```

Create a separate project directory and environment. Install the reviewed wheel
by absolute path, install pytest separately, and copy the reviewed source archive's
`examples/` package into that project. The distribution is `fracture-recovery`,
while import and CLI are `fracture`; do not coinstall the unrelated `fracture` package.
For example, in PowerShell (replace the two reviewed absolute paths):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install C:\reviewed\fracture_recovery-0.1.0-py3-none-any.whl
.venv\Scripts\python -m pip install 'pytest>=9,<10'
# Extract only from an archive you reviewed; inspect its contents first.
tar -tf C:\reviewed\fracture_recovery-0.1.0.tar.gz
tar -xf C:\reviewed\fracture_recovery-0.1.0.tar.gz fracture_recovery-0.1.0/examples
Copy-Item -Recurse fracture_recovery-0.1.0/examples ./examples
$env:PYTHONPATH = (Get-Location).Path
.venv\Scripts\python -m pytest examples/test_existing_workflow.py
.venv\Scripts\python -m examples.demo_recovery --output artifacts/order-demo-1
.venv\Scripts\fracture inspect artifacts/order-demo-1/negative/report.json
# The preceding inspect deliberately exits 1. Corrected inspection exits 0:
.venv\Scripts\fracture inspect artifacts/order-demo-1/corrected/report.json
```

On Linux use `.venv/bin/python`, `.venv/bin/fracture`, `cp -R` and
`export PYTHONPATH="$PWD"` for the same commands. No application credential is needed.
Every execution output directory must be new; inspect may repeatedly read the same file.

| Application concern | Executable mapping |
| --- | --- |
| Existing writes | `order_app.ship`: commits SQLite shipment rows; app imports no Fracture |
| Fresh disposable fixture | `OrderFixture.prepare/inspect/describe`; one business database per case |
| Truthful fault capability | `supports` and `verify_commit`: independent SELECT confirms committed receipt |
| Action wrapper | `workflow.write`: public `action("ship", ...)`, then `observe_commit` after commit |
| Stable identity | `identity`: order ID plus `shipment`; same identity across retry attempts |
| Durable checkpointer | `workflow` passes Fracture's supplied SQLite checkpointer to app builder |
| Business assertions | `effect_count("order-001", "ship")`, `terminal_outcome("completed")` |
| Explicit recovery | `LangGraphDriver(error_resumes=2, restart_on_process_exit=True)` |
| Ordinary pytest | `assert_campaign(corrected(), tmp_path / "corrected")`; no global plugin |

Measured adapter size is 83 physical lines, unchanged from the starting commit. It includes six
fixture methods, identity, workflow wrapper and scenario factories. This is a size
measurement, not a timed external integration trial; independent adapter effort
and adoption remain unmeasured. The app and adapter stay separate.

## Read evidence and fix the business write

The summary reports the baseline separately and lists failed assertion names/details,
operation/site/occurrence and targeted attempt, reached/applied flags, total action
attempts versus fixture-provided durable effects, confirmed worker termination and
restart, and saved checkpoint continuity where recorded. Unknown evidence is labeled
unknown. Effect totals are not inferred from assertion prose and are not a generic
proof of every custom assertion. Inspect evaluates recorded assertion results; it
does not rerun them, authenticate artifacts or verify a live backend.

Missing assertion results, non-valid cases, or required faults without reached/applied
evidence are INVALID in labels, recovery counts and inspection exits. Optional attempt,
backend and checkpoint details may remain unknown without invalidating a case.

`--case` selects an exact case ID from the report. It does not hide a failing baseline
or invalid case from the command exit status. Only schema-v1 campaign JSON is accepted;
replay JSON is a different artifact. Detailed `report.txt`, `timeline.txt`, `case.json`
and SQLite stores remain available. Inspect does not follow replay paths or open stores.

The negative app inserts on every retry: baseline and before-action pass, but both
post-commit cases produce two shipments and fail the effect assertion. The corrected
app deduplicates within `BEGIN IMMEDIATE` using stable order identity: baseline, all
three fault cases and replay preserve one effect. The driver validates these exact
outcomes, real kill/restart and the prior checkpoint on the same thread. Its educational
exit 0 means those expected controls held; normal test/replay semantics remain unchanged.

Compact output escapes controls, uses no color and excludes arbitrary snapshots,
results, receipts and event payloads. Custom assertion details, operation labels and
artifact paths may still expose sensitive data. Restrict artifact access, inspect
the entire capture, redact deliberately before sharing, and retain originals privately.
No universal redaction is promised. Scenarios and replay execute trusted Python.

## Reproduce an 80–88 second recording

From the checkout with frozen development dependencies installed:

```console
uv run python scripts/record_demo.py --output artifacts/recording-NEW
```

Record the terminal in plain text/no-color mode. The script saves the exact merged
stdout/stderr to `terminal.txt` and each command's real exit and duration to
`recording.json`. It runs an intentionally failing ordinary pytest test, the real
negative/corrected order campaigns, corrected replay, then read-only case inspection.
It checks actual exits (pytest/negative inspect 1, driver/corrected inspect 0).
It retains full reports and databases. It adds an explicitly labeled presentation
hold to target 84 seconds; it never removes execution waiting or invents output.
If execution exceeds 88 seconds, record the overrun and use clearly disclosed cuts
for a separate edited video. Do not label that edit as an uninterrupted capture.

Suggested narration: introduce the synthetic write and pytest assertion; show two
attempts/two effects after a lost response and worker kill; explain stable identity
and atomic deduplication; show corrected one effect, checkpoint continuation and
replay; finish with the independent-integration limitation. Use the final hold for
the explanation. Measurements and actual selected output are in
[milestone evidence](pytest-evidence-results.md) and [terminal capture](pytest-evidence-terminal.txt).
That saved capture and its artifacts predate the inspection-status review correction;
they do not validate the revised source or its replay fingerprint. Fresh build,
clean-install and remote checks are pending as recorded in the milestone evidence.

Unposted social draft:

> A retry isn't proof of a safe write. This synthetic LangGraph order test shows a
> lost response and a real worker kill duplicating a shipment. Atomic deduplication
> preserves one durable effect, with pytest evidence and checkpoint continuation.
> Fracture's inspect command reads saved reports without executing the application.
> Independent integration is still outstanding.

Unposted short draft:

> Two attempts, one durable shipment: a synthetic pytest recovery demo with real
> worker termination, explicit recovery, and read-only evidence inspection. No
> production safety guarantee; independent application validation is next.

The next milestone remains a licensed independently authored workflow with existing
durable writes: record revision/license, isolate adapter edits, measure effort,
validate meaningful corrected/negative controls and report blockers. Do not change
an external app to manufacture suitable behavior. UI work remains deferred.
