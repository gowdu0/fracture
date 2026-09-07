# Python integration contract

## Scenario construction

`Scenario(name, workflow, backend, driver, assertions, ...)` is ordinary Python
configuration. `workflow(context, checkpointer)` builds a compiled LangGraph graph
using the supplied durable checkpointer. Its node callables may be local closures;
the **factory itself** must be importable/picklable for multiprocessing spawn.
Pass paths/configuration, not live database connections, to backend and driver
objects. Setup/reset and final inspection execute in the controller.

`initial_input` is sent only for a new case. Recovery preserves the case directory,
thread identity, checkpoint database, and controller journal. `approvals` is a tuple
of application-specific JSON dictionaries delivered sequentially at interrupts.
`target="my_tests.scenarios:change"` identifies a zero-argument factory (or module
attribute containing a Scenario) for replay. It must reconstruct your assertions
and backend. Source hashes include the Fracture modules, scenario target, factory,
backend, driver, and assertion modules. Add other relevant files to `source_files`.
Transitive application imports are not automatically discovered.

For callable objects used as assertions, prefer top-level functions if you need
automatic source fingerprinting. A factory's in-memory modifications that cannot
be reconstructed should be moved into its source before claiming replay support.

## BackendFixture methods

| Method | Contract |
| --- | --- |
| `prepare(directory)` | Build a fresh fixture in a new case directory, without modifying other cases |
| `inspect(directory)` | Return a JSON-serializable snapshot of authoritative durable state/history |
| `describe()` | Return a deterministic fixture payload or reproducible reference; include all fixture parameters |
| `supports(site, fault)` | Explicitly declare each site's supported fault capabilities |
| `verify_commit(directory, receipt)` | Independently confirm the receipt through a durable backend read |
| `record_approval(directory, approval)` | Record the decision and its binding before delivery to the application |

The bundled fixture uses `application.sqlite`; Fracture reserves
`controller.sqlite`, `checkpoints.sqlite`, and `case.json` in each case directory.
Only the bundled fixture currently has validated process-exit support. For an
external service, returning a response or counting wrapper calls is not sufficient
to implement `verify_commit`. Never mark unsupported commit visibility as supported.

## Action instrumentation

Actual example from the installed support fixture:

```python
from fracture import action, observe_commit
from fracture.demo import identity

# identity(operation, *args, **kwargs) returns (operation, "primary").
# create_ticket in fracture.demo is decorated with:
# @action("create_ticket", identity=identity, commit_visible=True)
```

Use a distinct stable `site` for each logical action location. Your resolver receives
the same positional/keyword arguments as the wrapped callable and returns the
logical operation and a stable occurrence key (for example, an order line ID).
Retries reuse these values. The controller journal increments the attempt number.
Do not use a fresh UUID per attempt as the logical operation or occurrence key.

After your transaction commits, call `observe_commit(receipt)` inside the action.
`current_attempt()` exposes the attempt identity for durable evidence, and
`current_context()` exposes the case directory. A successful action declaring
commit visibility but omitting observation invalidates the test. Sync and async
wrappers preserve metadata; ordinary application exceptions propagate. The local
async ticket wrapper uses a short blocking SQLite transaction and makes no claim
of nonblocking SQLite I/O.

Outside a Fracture context, an action wrapper simply calls the original function.
`observe_commit` itself requires an active context; application-owned adapters
should invoke it only when instrumented testing is active. The bundled demo
backend is specifically a test fixture, not a production backend.

## Assertion snapshot shape

Built-ins consume these adapter-provided fields (custom assertions may use any shape):

- `effects`: records with `id`, `operation`, `action`, `resource`, `parameters`.
  Authorization checks additionally require a durable `sequence` comparable to
  approval sequence. Fixture effects also contain `attempt_id`.
- `approvals`: records with `approved` (a boolean), `operation`, `resource`,
  `parameters`, and `sequence`.
- `resources`: mapping of resource IDs to their selected final business fields.
- Additional top-level keys support `backend_state(expected, unchanged=...)`.

The graph result may include `claims`: records with `success`, `operation`,
`action`, `resource`, and `parameters`. Every successful claim is checked against
durable effects and final resource values. This check alone permits an empty claim
list; use `terminal_outcome`, `effect_count`, and custom assertions to enforce
required work. Do not treat validation of arbitrary natural-language text as implied.

An ordinary custom assertion accepts `CheckContext(initial, final, outcome, result,
events)`, raises `AssertionError` on a business violation, and otherwise returns
`None`. It may alternatively return an `InvariantResult`. Any other exception is a
checker/infrastructure error, preserving other invariant results.

## Recovery and execution

`LangGraphDriver(error_resumes=0, restart_on_process_exit=False)` is deliberately
explicit. `retry_exceptions` defaults to `(TimeoutError,)`; the driver resumes only
configured errors. The demo opts into two error resumes and process restarts.
`run_case` runs a single baseline or explicit fault; `run_campaign` runs a baseline
and automatic expansion (or a supplied `cases=[FaultCase(...)]`). Each case is
isolated in a spawned worker on Windows and Linux.

Use `arun_campaign` from async code. It runs the parent controller in a thread and
the graph with `AsyncSqliteSaver` in a worker. The watchdog still bounds worker
execution if the caller stops awaiting the controller; cancellation is not itself
a simulated crash. V1 requires dict graph state/results with JSON-serializable
evidence. Concurrent graph branches, nested concurrent tools, and concurrent
interrupts are outside the supported contract.

For scripts, place execution under `if __name__ == "__main__":`. Pytest and the
installed CLI already provide suitable process entrypoints. Start with
`fracture.testing.assert_campaign(scenario, tmp_path / "campaign")` to retain
artifacts and produce an actionable assertion failure in existing tests.
