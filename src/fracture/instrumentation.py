"""Explicit action identity and commit observation, with no inferred transactions."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast

from .journal import Journal
from .types import FaultCase, InfrastructureError, RecoveryExhausted, Scenario

F = TypeVar("F", bound=Callable[..., Any])
_context: ContextVar[RunContext | None] = ContextVar("fracture_context", default=None)
_attempt: ContextVar[dict[str, Any] | None] = ContextVar("fracture_attempt", default=None)


@dataclass
class RunContext:
    directory: Path
    scenario: Scenario
    journal: Journal
    thread_id: str
    fault: FaultCase | None
    pipe: Any

    def boundary(self, kind: str, attempt: dict[str, Any], **extra: Any) -> None:
        self.journal.event("boundary", boundary=kind, **attempt, **extra)
        fault = self.fault
        if fault is None or self.journal.get("fault_consumed", False):
            return
        target = fault.model_dump()
        if kind != target.pop("kind") or any(attempt.get(k) != v for k, v in target.items()):
            return
        self.journal.set("fault_reached", True)
        if kind == "after_commit_process_exit":
            self.pipe.send({"kind": "commit_barrier", "receipt": extra["receipt"]})
            # The controller never acknowledges this barrier; it kills this worker.
            self.pipe.recv()
            raise InfrastructureError("crash barrier unexpectedly released")
        self.journal.set("fault_consumed", True)
        self.journal.set("fault_applied", True)
        self.journal.event("fault_applied", fault=fault.model_dump())
        raise TimeoutError(f"Fracture injected {kind}")


def current_context() -> RunContext:
    context = _context.get()
    if context is None:
        raise InfrastructureError("no active Fracture run context")
    return context


def current_attempt() -> dict[str, Any]:
    value = _attempt.get()
    if value is None:
        raise InfrastructureError("commit observation must occur inside a registered action")
    return value


def observe_commit(receipt: dict[str, Any]) -> None:
    """Call AFTER a backend transaction commits, with verifiable durable effect evidence."""
    context, attempt = current_context(), current_attempt()
    if not attempt["commit_visible"]:
        raise InfrastructureError("action did not declare commit visibility")
    if not context.scenario.backend.verify_commit(context.directory, receipt):
        raise InfrastructureError("backend could not verify the supplied commit receipt")
    if attempt.get("committed"):
        raise InfrastructureError("v1 supports one commit observation per action invocation")
    attempt["committed"] = True
    context.boundary("after_commit_response_lost", attempt, receipt=receipt)
    context.boundary("after_commit_process_exit", attempt, receipt=receipt)


def action(
    site: str, *, identity: Callable[..., tuple[str, str]], commit_visible: bool = False
) -> Callable[[F], F]:
    """identity(*args, **kwargs) returns (logical_operation, stable_occurrence_key)."""
    if not site:
        raise ValueError("action site must be nonempty")

    def decorate(function: F) -> F:
        if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
            raise ValueError("generator and streaming actions are unsupported")

        def begin(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[RunContext, Any]:
            context = current_context()
            operation, occurrence = identity(*args, **kwargs)
            if not operation or not occurrence:
                raise InfrastructureError("operation and occurrence must be nonempty")
            key = json.dumps([operation, site, occurrence])
            number = context.journal.next_attempt(key)
            record = dict(
                operation=operation,
                site=site,
                occurrence=occurrence,
                attempt=number,
                attempt_id=f"{key}:{number}",
                commit_visible=commit_visible,
            )
            context.journal.event("attempt", **record)
            if number > context.scenario.budgets.attempts:
                raise RecoveryExhausted(f"attempt budget exhausted: {key}")
            return context, _attempt.set(record)

        def complete(context: RunContext) -> None:
            record = current_attempt()
            if commit_visible and not record.get("committed"):
                raise InfrastructureError(f"{site}: successful action omitted commit observation")
            context.journal.event("response_returned", **record)

        @wraps(function)
        def sync(*args: Any, **kwargs: Any) -> Any:
            if _context.get() is None:
                return function(*args, **kwargs)
            context, token = begin(args, kwargs)
            try:
                context.boundary("before_action", current_attempt())
                result = function(*args, **kwargs)
                complete(context)
                return result
            finally:
                _attempt.reset(token)

        @wraps(function)
        async def asynchronous(*args: Any, **kwargs: Any) -> Any:
            if _context.get() is None:
                return await function(*args, **kwargs)
            context, token = begin(args, kwargs)
            try:
                context.boundary("before_action", current_attempt())
                result = await function(*args, **kwargs)
                complete(context)
                return result
            finally:
                _attempt.reset(token)

        return cast(F, asynchronous if inspect.iscoroutinefunction(function) else sync)

    return decorate
