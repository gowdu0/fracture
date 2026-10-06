# Adoption and release validation guide

The README install-to-test path uses a synthetic external-style example, not proof
of independent adoption. For a reviewed source checkout, run:

```console
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest examples/test_existing_workflow.py
uv run python -m examples.demo_recovery --output artifacts/order-demo
uv run fracture inspect artifacts/order-demo/corrected/report.json
# Make the example importable: PYTHONPATH=project root (see README shell commands).
uv run fracture test examples.order_adapter:corrected --output artifacts/orders
uv run fracture replay artifacts/orders/replay.json --output artifacts/orders-replay
uv run fracture demo --output artifacts/full-demo
uv build
uv run python scripts/check_reproducible.py
uv run python scripts/check_release.py --output artifacts/install-check
uv run python scripts/audit_runtime.py --output artifacts/audit
```

Every output must be fresh, including `artifacts/reproducible.json`. Keep artifact
checks under `artifacts/install-check` so the audit helper can find both resolved
runtime exports. If repeating, use a fresh output path and pass
`--install-evidence <that path>` to the audit helper. The helpers validate
sdist/wheel metadata and contents, record SHA-256 hashes, compare rebuild bytes,
and install each artifact into a fresh temporary environment outside the checkout.
They read only the five required example files from the built sdist for both
installation paths, invoke the actual console executable with Git absent from PATH,
and assert dev packages are
absent. They test positive/negative replay and installed read-only inspection
(including exit 0/1/2), downstream typing (in a separate mypy
tool environment), then install pytest separately and run the example tests.

CI retains Windows/Linux × Python 3.12/3.13. Local evidence states exact environments;
workflow changes are not remote CI results. Audit failures and unavailable environments
must be recorded. See the release checklist before any publication.

## Trials of independently authored applications

This remains a guide for future trials, not evidence that users have completed them.

1. Choose an existing sequential LangGraph test with a meaningful durable write.
   Identify the logical operation, its expected effect count, and any approval binding.
2. Supply fresh backend fixtures and a factory using the provided checkpointer.
   Register one action boundary. Declare post-commit capabilities only when your
   backend can independently verify a committed effect.
3. Reuse existing business assertions. Explicitly configure the application's
   actual recovery policy. Confirm its unfaulted baseline first.
4. Run a bounded campaign. Inspect one fault's reached/applied evidence, attempts,
   effect IDs, and backend differences. Confirm invalid cases cannot pass.
5. Reproduce a controlled failure with the saved replay command. Record any setup
   friction, missing capabilities, and source/environment mismatch diagnostics.
6. Decide whether the added defect detection warrants keeping the test in CI.
   Record integration files/lines, behavior covered, assertions reused, runtime
   actually measured, and whether the failure was original or a planted mutation.

Useful feedback: Which real assertion changed a decision? Which adapter requirement
was hardest? Was the report enough to fix or dismiss the result? Would you keep
this test after the trial? No outreach has been performed.
