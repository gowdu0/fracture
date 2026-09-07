"""An explicit, sequential application recovery driver using public LangGraph APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from .instrumentation import RunContext
from .types import InfrastructureError, RecoveryExhausted


@dataclass(frozen=True)
class LangGraphDriver:
    error_resumes: int = 0
    retry_exceptions: tuple[type[Exception], ...] = (TimeoutError,)
    restart_on_process_exit: bool = False

    def __post_init__(self) -> None:
        if self.error_resumes < 0:
            raise ValueError("error_resumes must be nonnegative")

    def describe(self) -> dict[str, Any]:
        return {
            "type": "LangGraphDriver",
            "error_resumes": self.error_resumes,
            "retry_exceptions": [f"{t.__module__}.{t.__qualname__}" for t in self.retry_exceptions],
            "restart_on_process_exit": self.restart_on_process_exit,
            "durability": "sync",
        }

    def config(self, context: RunContext) -> dict[str, Any]:
        remaining = context.scenario.budgets.steps - context.journal.get("steps", 0)
        if remaining < 1:
            raise RecoveryExhausted("graph step budget exhausted")
        return {"configurable": {"thread_id": context.thread_id}, "recursion_limit": remaining}

    def checkpoint(self, context: RunContext, snapshot: Any, phase: str) -> None:
        context.journal.event(
            "checkpoint",
            phase=phase,
            config=snapshot.config,
            next=list(snapshot.next),
            metadata=snapshot.metadata,
        )

    def update(self, context: RunContext, update: dict[str, Any]) -> None:
        nodes = [key for key in update if not key.startswith("__")]
        if nodes:
            steps = context.journal.get("steps", 0) + len(nodes)
            context.journal.set("steps", steps)
            context.journal.event("steps", nodes=nodes, total=steps)
            if steps > context.scenario.budgets.steps:
                raise RecoveryExhausted("graph step budget exhausted")

    def continuation(self, context: RunContext, snapshot: Any) -> tuple[bool, Any]:
        interrupts = [i for task in snapshot.tasks for i in task.interrupts]
        if not interrupts:
            if snapshot.next:
                raise InfrastructureError("driver stopped with pending nodes and no interrupt")
            return False, {
                "outcome": snapshot.values.get("outcome", "completed"),
                "result": snapshot.values,
            }
        context.journal.event(
            "approval_interrupt",
            interrupts=[{"id": item.id, "value": item.value} for item in interrupts],
        )
        if len(interrupts) != 1:
            raise InfrastructureError("concurrent approval interrupts are unsupported in v1")
        index = context.journal.get("approval_index", 0)
        if index >= len(context.scenario.approvals):
            return False, {"outcome": "interrupted", "result": snapshot.values}
        approval = context.scenario.approvals[index]
        context.scenario.backend.record_approval(context.directory, approval)
        context.journal.event(
            "approval_delivered", approval=approval, interrupt_id=interrupts[0].id
        )
        context.journal.set("approval_index", index + 1)
        return True, Command(resume=approval)

    def failure(self, context: RunContext, error: Exception) -> tuple[bool, Any]:
        if isinstance(error, InfrastructureError):
            raise error
        context.journal.event(
            "application_exception", type=type(error).__name__, message=str(error)
        )
        if isinstance(error, (RecoveryExhausted, GraphRecursionError)):
            return False, {"outcome": "recovery-exhausted", "result": {"error": str(error)}}
        if isinstance(error, self.retry_exceptions):
            used = context.journal.get("error_resumes", 0)
            if used < self.error_resumes:
                context.journal.set("error_resumes", used + 1)
                context.journal.event("error_resume", input=None, number=used + 1)
                return True, None
            outcome = "recovery-exhausted" if self.error_resumes else "failed"
            return False, {"outcome": outcome, "result": {"error": str(error)}}
        return False, {"outcome": "failed", "result": {"error": str(error)}}

    def run(self, graph: Any, context: RunContext, *, resume: bool) -> dict[str, Any]:
        value = None if resume else context.scenario.initial_input
        while True:
            try:
                config = self.config(context)
                self.checkpoint(context, graph.get_state(config), "before")
                for update in graph.stream(value, config, stream_mode="updates", durability="sync"):
                    self.update(context, update)
                snapshot = graph.get_state(config)
                self.checkpoint(context, snapshot, "after")
                again, value = self.continuation(context, snapshot)
            except Exception as error:
                again, value = self.failure(context, error)
            if not again:
                return dict(value)

    async def arun(self, graph: Any, context: RunContext, *, resume: bool) -> dict[str, Any]:
        value = None if resume else context.scenario.initial_input
        while True:
            try:
                config = self.config(context)
                self.checkpoint(context, await graph.aget_state(config), "before")
                async for update in graph.astream(
                    value, config, stream_mode="updates", durability="sync"
                ):
                    self.update(context, update)
                snapshot = await graph.aget_state(config)
                self.checkpoint(context, snapshot, "after")
                again, value = self.continuation(context, snapshot)
            except Exception as error:
                again, value = self.failure(context, error)
            if not again:
                return dict(value)
