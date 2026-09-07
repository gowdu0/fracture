"""Small Python integration contract and versioned report models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

FaultKind = Literal["before_action", "after_commit_response_lost", "after_commit_process_exit"]
FAULTS: tuple[FaultKind, ...] = (
    "before_action",
    "after_commit_response_lost",
    "after_commit_process_exit",
)
Outcome = Literal["completed", "interrupted", "rejected", "failed", "recovery-exhausted"]
Validity = Literal[
    "valid", "unsupported", "unreached", "infrastructure-error", "configuration-error"
]


class InfrastructureError(RuntimeError):
    """An invalid test execution, distinct from an application failure."""


class RecoveryExhausted(RuntimeError):
    """The configured application execution budget has been exhausted."""


@dataclass(frozen=True)
class Budgets:
    steps: int = 100
    attempts: int = 3
    restarts: int = 2
    cases: int = 32
    seconds: float = 60

    def __post_init__(self) -> None:
        if min(self.steps, self.attempts, self.cases) < 1 or self.restarts < 0 or self.seconds <= 0:
            raise ValueError("budgets must be positive (restarts may be zero)")


class BackendFixture(Protocol):
    def prepare(self, directory: Path) -> None: ...
    def inspect(self, directory: Path) -> dict[str, Any]: ...
    def describe(self) -> dict[str, Any]: ...
    def supports(self, site: str, fault: FaultKind) -> bool: ...
    def verify_commit(self, directory: Path, receipt: dict[str, Any]) -> bool: ...
    def record_approval(self, directory: Path, approval: dict[str, Any]) -> None: ...


class RecoveryDriver(Protocol):
    @property
    def restart_on_process_exit(self) -> bool: ...

    def run(self, graph: Any, context: Any, *, resume: bool) -> dict[str, Any]: ...
    async def arun(self, graph: Any, context: Any, *, resume: bool) -> dict[str, Any]: ...
    def describe(self) -> dict[str, Any]: ...


@dataclass
class CheckContext:
    initial: dict[str, Any]
    final: dict[str, Any]
    outcome: Outcome
    result: dict[str, Any]
    events: list[dict[str, Any]]


@dataclass
class Scenario:
    name: str
    workflow: Callable[..., Any]
    backend: BackendFixture
    driver: RecoveryDriver
    assertions: tuple[Callable[[CheckContext], Any], ...]
    initial_input: dict[str, Any] = field(default_factory=dict)
    approvals: tuple[dict[str, Any], ...] = ()
    budgets: Budgets = field(default_factory=Budgets)
    faults: tuple[FaultKind, ...] = FAULTS
    asynchronous: bool = False
    continue_failed_baseline: bool = False
    version: str = "1"
    source_files: tuple[str, ...] = ()
    target: str | None = None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FaultCase(Model):
    kind: FaultKind
    operation: str
    site: str
    occurrence: str
    attempt: int = Field(default=1, ge=1)

    @property
    def id(self) -> str:
        import hashlib

        digest = hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]
        return f"{self.kind}-{digest}"


class InvariantResult(Model):
    name: str
    passed: bool
    detail: str = ""


class CaseReport(Model):
    id: str
    validity: Validity = "valid"
    outcome: Outcome = "failed"
    fault: FaultCase | None = None
    reached: bool = False
    applied: bool = False
    diagnostic: str = ""
    invariants: list[InvariantResult] = Field(default_factory=list)
    initial: dict[str, Any] = Field(default_factory=dict)
    final: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    thread_id: str = ""
    processes: list[dict[str, Any]] = Field(default_factory=list)
    backend_diff: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            self.validity == "valid"
            and bool(self.invariants)
            and all(item.passed for item in self.invariants)
        )


class CampaignReport(Model):
    schema_version: Literal[1] = 1
    scenario: str
    cases: list[CaseReport] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    replay_path: str | None = None

    @property
    def exit_code(self) -> int:
        if self.errors or not self.cases or any(c.validity != "valid" for c in self.cases):
            return 2
        return 0 if all(c.passed for c in self.cases) else 1


class ReplaySpec(Model):
    schema_version: Literal[1] = 1
    target: str
    fingerprint: dict[str, Any]
    fixture: dict[str, Any]
    configuration: dict[str, Any]
    cases: list[FaultCase]
    expected: list[dict[str, Any]]
