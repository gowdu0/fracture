# Prospective-user validation guide

This is a guide for future trials, not evidence that users have completed them.

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
