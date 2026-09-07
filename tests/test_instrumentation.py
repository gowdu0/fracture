"""Contract failures and idempotency behavior at real SQLite transaction boundaries."""

import asyncio
import inspect

import pytest

from fracture import InfrastructureError, action, observe_commit
from fracture.demo import OPERATION, RESOURCE, approved_change, create_ticket, identity
from fracture.instrumentation import RunContext, _attempt, _context
from fracture.journal import Journal


@pytest.fixture
def active_context(tmp_path):
    scenario = approved_change()
    scenario.backend.prepare(tmp_path)
    journal = Journal(tmp_path / "controller.sqlite")
    journal.initialize()
    context = RunContext(tmp_path, scenario, journal, "contract", None, None)
    token = _context.set(context)
    try:
        yield context
    finally:
        _context.reset(token)


def test_atomic_dedup_returns_original_result_and_rejects_parameter_reuse(active_context):
    first = create_ticket(OPERATION, RESOURCE, idempotent=True)
    second = create_ticket(OPERATION, RESOURCE, idempotent=True)
    assert first == second
    snapshot = active_context.scenario.backend.inspect(active_context.directory)
    assert len(snapshot["effects"]) == len(snapshot["tickets"]) == 1
    with pytest.raises(ValueError, match="different business parameters"):
        create_ticket(OPERATION, "customer_002", idempotent=True)
    after = active_context.scenario.backend.inspect(active_context.directory)
    assert after == snapshot


def test_new_idempotency_key_per_attempt_still_creates_duplicate_effects(active_context):
    from fracture.assertions import effect_count
    from fracture.types import CheckContext

    backend = active_context.scenario.backend
    for attempt in (1, 2):
        token = _attempt.set({"attempt_id": str(attempt)})
        try:
            backend.write(
                active_context.directory,
                OPERATION,
                "create_ticket",
                RESOURCE,
                {},
                key=f"new-key-{attempt}",
            )
        finally:
            _attempt.reset(token)
    snapshot = backend.inspect(active_context.directory)
    result = effect_count(OPERATION, "create_ticket")(
        CheckContext({}, snapshot, "completed", {}, [])
    )
    assert not result.passed


def test_missing_commit_visibility_is_a_diagnostic(active_context):
    @action("omitted", identity=identity, commit_visible=True)
    def omitted(operation):
        return "a response is not commit evidence"

    with pytest.raises(InfrastructureError, match="omitted commit observation"):
        omitted(OPERATION)


def test_unverified_commit_is_never_accepted(active_context):
    @action("false-receipt", identity=identity, commit_visible=True)
    def false_receipt(operation):
        observe_commit(
            {
                "effect_id": 999,
                "operation": operation,
                "action": "create_ticket",
                "resource": RESOURCE,
                "parameters": {},
            }
        )

    with pytest.raises(InfrastructureError, match="could not verify"):
        false_receipt(OPERATION)
    assert active_context.scenario.backend.inspect(active_context.directory)["effects"] == []


def test_sync_and_async_wrappers_preserve_metadata_and_original_exceptions(active_context):
    error = LookupError("original application error")

    def source(operation: str) -> int:
        """Original documentation."""
        raise error

    wrapped = action("sync", identity=identity)(source)
    assert wrapped.__name__ == source.__name__
    assert inspect.signature(wrapped) == inspect.signature(source)
    assert wrapped.__doc__ == source.__doc__
    with pytest.raises(LookupError) as caught:
        wrapped(OPERATION)
    assert caught.value is error

    async def asource(operation: str) -> int:
        raise error

    awrapped = action("async", identity=identity)(asource)
    assert inspect.iscoroutinefunction(awrapped)
    with pytest.raises(LookupError) as caught:
        asyncio.run(awrapped(OPERATION))
    assert caught.value is error


def test_generators_are_explicitly_unsupported():
    def generator(operation):
        yield operation

    with pytest.raises(ValueError, match="unsupported"):
        action("generator", identity=identity)(generator)
