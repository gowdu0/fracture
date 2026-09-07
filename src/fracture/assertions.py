"""Business assertions over adapter-provided durable evidence, never call counts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .types import CheckContext, InvariantResult

Assertion = Callable[[CheckContext], InvariantResult]


def _matches(row: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(row.get(key) == value for key, value in expected.items())


def effect_count(
    operation: str,
    action: str,
    expected: int | tuple[int, int] = 1,
    *,
    parameters: dict[str, Any] | None = None,
) -> Assertion:
    lower, upper = (expected, expected) if isinstance(expected, int) else expected
    if not 0 <= lower <= upper:
        raise ValueError("invalid effect count range")

    def check(context: CheckContext) -> InvariantResult:
        effects = [
            e
            for e in context.final["effects"]
            if e["operation"] == operation
            and e["action"] == action
            and _matches(e["parameters"], parameters or {})
        ]
        return InvariantResult(
            name=f"effect_count:{operation}/{action}",
            passed=lower <= len(effects) <= upper,
            detail=f"expected {lower}..{upper} durable effects; actual {len(effects)}",
        )

    return check


def authorized_effect(action: str) -> Assertion:
    def check(context: CheckContext) -> InvariantResult:
        violations = []
        for effect in context.final["effects"]:
            if effect["action"] != action:
                continue
            matches = [
                a
                for a in context.final["approvals"]
                if a.get("approved") is True
                and a["operation"] == effect["operation"]
                and a["resource"] == effect["resource"]
                and a["parameters"] == effect["parameters"]
                and a["sequence"] < effect["sequence"]
            ]
            if not matches:
                violations.append(effect["id"])
        return InvariantResult(
            name=f"authorized_effect:{action}",
            passed=not violations,
            detail=f"effects without prior matching approval: {violations}",
        )

    return check


def backend_state(expected: dict[str, Any], *, unchanged: tuple[str, ...] = ()) -> Assertion:
    """Compare selected top-level snapshot keys (adapters choose their stable projection)."""

    def check(context: CheckContext) -> InvariantResult:
        differences = [key for key, value in expected.items() if context.final.get(key) != value]
        differences += [
            key for key in unchanged if context.initial.get(key) != context.final.get(key)
        ]
        return InvariantResult(
            name="backend_state",
            passed=not differences,
            detail=f"mismatched snapshot keys: {differences}",
        )

    return check


def terminal_outcome(*allowed: str) -> Assertion:
    if not allowed:
        raise ValueError("at least one terminal outcome is required")

    def check(context: CheckContext) -> InvariantResult:
        return InvariantResult(
            name="terminal_outcome",
            passed=context.outcome in allowed,
            detail=f"expected {allowed}; actual {context.outcome}",
        )

    return check


def structured_claim_matches_state() -> Assertion:
    """Successful structured claims need this operation's effect AND matching final state."""

    def check(context: CheckContext) -> InvariantResult:
        bad = []
        for claim in context.result.get("claims", []):
            if claim.get("success") is not True:
                continue
            matching = any(
                e["operation"] == claim["operation"]
                and e["action"] == claim["action"]
                and e["resource"] == claim["resource"]
                and e["parameters"] == claim["parameters"]
                for e in context.final["effects"]
            )
            state_matches = _matches(
                context.final["resources"].get(claim["resource"], {}), claim["parameters"]
            )
            if not matching or not state_matches:
                bad.append(claim)
        return InvariantResult(
            name="structured_claim_matches_state",
            passed=not bad,
            detail=f"unsupported successful claims: {bad}",
        )

    return check
