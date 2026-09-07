"""Deterministic support workflow exercising agent execution machinery without an LLM."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .assertions import (
    authorized_effect,
    backend_state,
    effect_count,
    structured_claim_matches_state,
    terminal_outcome,
)
from .instrumentation import RunContext, action, current_attempt, current_context, observe_commit
from .langgraph import LangGraphDriver
from .types import FAULTS, FaultKind, Scenario

OPERATION = "change_request_001"
RESOURCE = "customer_001"
PARAMETERS = {"plan": "pro"}


@dataclass(frozen=True)
class SQLiteBackend:
    fail_update: bool = False
    capabilities: tuple[FaultKind, ...] = FAULTS

    def prepare(self, directory: Path) -> None:
        with sqlite3.connect(directory / "application.sqlite") as db:
            db.executescript("""
                CREATE TABLE customers (id TEXT PRIMARY KEY, plan TEXT, email TEXT);
                INSERT INTO customers VALUES ('customer_001','basic','one@example.test');
                INSERT INTO customers VALUES ('customer_002','basic','two@example.test');
                CREATE TABLE tickets (id INTEGER PRIMARY KEY, operation TEXT, customer TEXT);
                CREATE TABLE notes (id INTEGER PRIMARY KEY, ticket INTEGER, note TEXT);
                CREATE TABLE audit (sequence INTEGER PRIMARY KEY, kind TEXT NOT NULL);
                CREATE TABLE approvals (id TEXT PRIMARY KEY, operation TEXT, resource TEXT,
                    approved INTEGER, parameters TEXT, sequence INTEGER UNIQUE);
                CREATE TABLE effects (id INTEGER PRIMARY KEY, operation TEXT, action TEXT,
                    resource TEXT, parameters TEXT, sequence INTEGER UNIQUE, attempt_id TEXT);
                CREATE TABLE dedup (key TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    effect_id INTEGER, result TEXT);
            """)

    def describe(self) -> dict[str, Any]:
        return {
            "type": "SQLiteBackend",
            "fixture_version": 1,
            "fail_update": self.fail_update,
            "capabilities": list(self.capabilities),
            "customers": [
                {"id": RESOURCE, "plan": "basic", "email": "one@example.test"},
                {"id": "customer_002", "plan": "basic", "email": "two@example.test"},
            ],
        }

    def supports(self, site: str, fault: FaultKind) -> bool:
        return fault in self.capabilities and site in (
            "create_ticket",
            "update_account",
            "add_note",
        )

    def inspect(self, directory: Path) -> dict[str, Any]:
        with sqlite3.connect(directory / "application.sqlite") as db:
            db.row_factory = sqlite3.Row

            def rows(table: str) -> list[dict[str, Any]]:
                # Table names are internal constants, not user-controlled identifiers.
                values = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for value in values:
                    if "parameters" in value:
                        value["parameters"] = json.loads(value["parameters"])
                    if "approved" in value:
                        value["approved"] = bool(value["approved"])
                return values

            customers = rows("customers")
            return {
                "customers": customers,
                "tickets": rows("tickets"),
                "notes": rows("notes"),
                "approvals": rows("approvals"),
                "effects": rows("effects"),
                "resources": {
                    row["id"]: {"plan": row["plan"], "email": row["email"]} for row in customers
                },
                "unrelated_customer": customers[1],
                "customer_plan": customers[0]["plan"],
                "customer_email": customers[0]["email"],
            }

    def record_approval(self, directory: Path, approval: dict[str, Any]) -> None:
        with sqlite3.connect(directory / "application.sqlite") as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT 1 FROM approvals WHERE id=?", (approval["id"],)
            ).fetchone()
            if existing:
                raise ValueError("approval IDs must be unique within a run")
            sequence = db.execute("INSERT INTO audit(kind) VALUES ('approval')").lastrowid
            db.execute(
                "INSERT INTO approvals VALUES (?,?,?,?,?,?)",
                (
                    approval["id"],
                    approval["operation"],
                    approval["resource"],
                    approval["approved"],
                    json.dumps(approval["parameters"], sort_keys=True),
                    sequence,
                ),
            )

    def verify_commit(self, directory: Path, receipt: dict[str, Any]) -> bool:
        with sqlite3.connect(directory / "application.sqlite") as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM effects WHERE id=?", (receipt.get("effect_id"),)
            ).fetchone()
            return (
                row is not None
                and all(row[key] == receipt.get(key) for key in ("operation", "action", "resource"))
                and (json.loads(row["parameters"]) == receipt.get("parameters"))
            )

    def write(
        self,
        directory: Path,
        operation: str,
        name: str,
        resource: str,
        parameters: dict[str, Any],
        *,
        key: str | None,
    ) -> dict[str, Any]:
        if name == "update_account" and self.fail_update:
            raise OSError("synthetic account backend refused update")
        payload = json.dumps([operation, name, resource, parameters], sort_keys=True)
        with sqlite3.connect(directory / "application.sqlite") as db:
            db.execute("BEGIN IMMEDIATE")
            if key is not None:
                inserted = db.execute(
                    "INSERT INTO dedup(key,payload) VALUES (?,?) "
                    "ON CONFLICT(key) DO NOTHING RETURNING key",
                    (key, payload),
                ).fetchone()
                if inserted is None:
                    stored_payload, effect_id, result = db.execute(
                        "SELECT payload,effect_id,result FROM dedup WHERE key=?", (key,)
                    ).fetchone()
                    if stored_payload != payload:
                        raise ValueError(
                            "idempotency key reused with different business parameters"
                        )
                    return {
                        "effect_id": effect_id,
                        "operation": operation,
                        "action": name,
                        "resource": resource,
                        "parameters": parameters,
                        "result": json.loads(result),
                        "deduplicated": True,
                    }
            if name == "create_ticket":
                ticket_id = db.execute(
                    "INSERT INTO tickets(operation,customer) VALUES (?,?)", (operation, resource)
                ).lastrowid
                result_value: Any = ticket_id
            elif name == "update_account":
                cursor = db.execute(
                    "UPDATE customers SET plan=? WHERE id=?", (parameters["plan"], resource)
                )
                if cursor.rowcount != 1:
                    raise ValueError("customer not found")
                result_value = parameters
            elif name == "add_note":
                result_value = db.execute(
                    "INSERT INTO notes(ticket,note) VALUES (?,?)",
                    (parameters["ticket"], parameters["note"]),
                ).lastrowid
            else:
                raise ValueError(f"unknown fixture action: {name}")
            sequence = db.execute("INSERT INTO audit(kind) VALUES ('effect')").lastrowid
            effect_id = db.execute(
                "INSERT INTO effects(operation,action,resource,parameters,sequence,attempt_id) "
                "VALUES (?,?,?,?,?,?)",
                (
                    operation,
                    name,
                    resource,
                    json.dumps(parameters, sort_keys=True),
                    sequence,
                    current_attempt()["attempt_id"],
                ),
            ).lastrowid
            if key is not None:
                db.execute(
                    "UPDATE dedup SET effect_id=?,result=? WHERE key=?",
                    (effect_id, json.dumps(result_value), key),
                )
        # Business mutation, deduplication, and evidence have committed before observation.
        return {
            "effect_id": effect_id,
            "operation": operation,
            "action": name,
            "resource": resource,
            "parameters": parameters,
            "result": result_value,
            "deduplicated": False,
        }


def identity(operation: str, *args: Any, **kwargs: Any) -> tuple[str, str]:
    return operation, "primary"


def _write(
    operation: str, site: str, resource: str, parameters: dict[str, Any], idempotent: bool
) -> Any:
    context = current_context()
    backend = context.scenario.backend
    if not isinstance(backend, SQLiteBackend):
        raise TypeError("support demo requires SQLiteBackend")
    key = json.dumps([operation, site, "primary"]) if idempotent else None
    receipt = backend.write(context.directory, operation, site, resource, parameters, key=key)
    observe_commit(receipt)
    return receipt["result"]


@action("create_ticket", identity=identity, commit_visible=True)
def create_ticket(operation: str, resource: str, *, idempotent: bool) -> int:
    return int(_write(operation, "create_ticket", resource, {}, idempotent))


@action("update_account", identity=identity, commit_visible=True)
def update_account(operation: str, resource: str, parameters: dict[str, Any]) -> None:
    _write(operation, "update_account", resource, parameters, True)


@action("add_note", identity=identity, commit_visible=True)
def add_note(operation: str, resource: str, ticket: int) -> None:
    _write(operation, "add_note", resource, {"ticket": ticket, "note": "Plan change applied"}, True)


@action("create_ticket", identity=identity, commit_visible=True)
async def acreate_ticket(operation: str, resource: str, *, idempotent: bool) -> int:
    # Deliberately tiny local sqlite3 operation. The workflow and wrapper use genuine async calls.
    return int(_write(operation, "create_ticket", resource, {}, idempotent))


class SupportState(TypedDict, total=False):
    operation: str
    resource: str
    parameters: dict[str, Any]
    customer: dict[str, Any]
    ticket: int
    approved: bool
    outcome: str
    claims: list[dict[str, Any]]
    message: str


def build_workflow(context: RunContext, checkpointer: Any, *, variant: str = "corrected") -> Any:
    idempotent = variant not in ("approval_replay", "split_only")

    def lookup(state: SupportState) -> dict[str, Any]:
        resources = context.scenario.backend.inspect(context.directory)["resources"]
        return {"customer": resources[state["resource"]]}

    def ticket(state: SupportState) -> dict[str, Any]:
        return {
            "ticket": create_ticket(state["operation"], state["resource"], idempotent=idempotent)
        }

    async def async_ticket(state: SupportState) -> dict[str, Any]:
        return {
            "ticket": await acreate_ticket(
                state["operation"], state["resource"], idempotent=idempotent
            )
        }

    def approval(state: SupportState) -> dict[str, Any]:
        extra = ticket(state) if variant == "approval_replay" else {}
        decision = interrupt(
            {
                "operation": state["operation"],
                "resource": state["resource"],
                "parameters": state["parameters"],
            }
        )
        matches = (
            decision.get("approved") is True
            and decision.get("operation") == state["operation"]
            and decision.get("resource") == state["resource"]
            and decision.get("parameters") == state["parameters"]
        )
        return {**extra, "approved": True if variant == "unauthorized" else matches}

    def update(state: SupportState) -> dict[str, Any]:
        try:
            update_account(state["operation"], state["resource"], state["parameters"])
        except OSError as error:
            # TimeoutError is an OSError too; it must propagate to the configured recovery driver.
            if isinstance(error, TimeoutError):
                raise
            if variant != "false_success":
                return {"outcome": "failed", "claims": [], "message": "Account change failed."}
        claim = {
            "success": True,
            "operation": state["operation"],
            "action": "update_account",
            "resource": state["resource"],
            "parameters": state["parameters"],
        }
        return {"outcome": "completed", "claims": [claim]}

    def note(state: SupportState) -> dict[str, Any]:
        add_note(state["operation"], state["resource"], state["ticket"])
        return {}

    def finish(state: SupportState) -> dict[str, Any]:
        # Prose is a projection of structured outcome, not an independently generated claim.
        messages = {
            "completed": "Account plan changed successfully.",
            "rejected": "Account change was not approved.",
            "failed": "Account change failed.",
        }
        outcome = state.get("outcome", "rejected")
        return {"outcome": outcome, "message": messages[outcome]}

    builder = StateGraph(SupportState)
    builder.add_node("lookup", lookup)
    builder.add_node("ticket", async_ticket if context.scenario.asynchronous else ticket)
    builder.add_node("approval", approval)
    builder.add_node("update", update)
    builder.add_node("note", note)
    builder.add_node("finish", finish)
    builder.add_edge(START, "lookup")
    builder.add_edge("lookup", "approval" if variant == "approval_replay" else "ticket")
    builder.add_edge("ticket", "approval")
    builder.add_conditional_edges("approval", lambda s: "update" if s["approved"] else "finish")
    builder.add_conditional_edges(
        "update", lambda s: "note" if s["outcome"] == "completed" else "finish"
    )
    builder.add_edge("note", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)


def make_scenario(
    name: str,
    *,
    variant: str = "corrected",
    approval_kind: str = "approved",
    fail_update: bool = False,
    asynchronous: bool = False,
) -> Scenario:
    decision = {
        "id": "approval_001",
        "operation": OPERATION,
        "resource": RESOURCE,
        "parameters": PARAMETERS,
        "approved": approval_kind != "rejected",
    }
    if approval_kind == "wrong_customer":
        decision["resource"] = "customer_002"
    elif approval_kind == "wrong_parameters":
        decision["parameters"] = {"plan": "enterprise"}
    elif approval_kind == "wrong_operation":
        decision["operation"] = "another_request"
    allowed = approval_kind == "approved"
    effect_expected = int(allowed and not fail_update)
    expected_outcome = "rejected" if not allowed else "failed" if fail_update else "completed"
    assertions = (
        effect_count(OPERATION, "create_ticket"),
        effect_count(OPERATION, "update_account", effect_expected, parameters=PARAMETERS),
        effect_count(OPERATION, "add_note", effect_expected),
        authorized_effect("update_account"),
        backend_state(
            {"customer_plan": "pro" if effect_expected else "basic"},
            unchanged=("unrelated_customer", "customer_email"),
        ),
        terminal_outcome(expected_outcome),
        structured_claim_matches_state(),
    )
    return Scenario(
        name=name,
        workflow=partial(build_workflow, variant=variant),
        backend=SQLiteBackend(fail_update=fail_update),
        driver=LangGraphDriver(error_resumes=2, restart_on_process_exit=True),
        assertions=assertions,
        initial_input={"operation": OPERATION, "resource": RESOURCE, "parameters": PARAMETERS},
        approvals=(decision,),
        asynchronous=asynchronous,
        target=f"fracture.demo:{name}",
    )


def approved_change() -> Scenario:
    return make_scenario("approved_change")


def approval_replay() -> Scenario:
    return make_scenario("approval_replay", variant="approval_replay")


def split_only() -> Scenario:
    return make_scenario("split_only", variant="split_only")


def rejected() -> Scenario:
    return make_scenario("rejected", approval_kind="rejected")


def wrong_customer() -> Scenario:
    return make_scenario("wrong_customer", approval_kind="wrong_customer")


def wrong_parameters() -> Scenario:
    return make_scenario("wrong_parameters", approval_kind="wrong_parameters")


def wrong_operation() -> Scenario:
    return make_scenario("wrong_operation", approval_kind="wrong_operation")


def unauthorized() -> Scenario:
    return make_scenario("unauthorized", variant="unauthorized", approval_kind="rejected")


def mismatched_unauthorized() -> Scenario:
    return make_scenario(
        "mismatched_unauthorized", variant="unauthorized", approval_kind="wrong_customer"
    )


def false_success() -> Scenario:
    return make_scenario("false_success", variant="false_success", fail_update=True)


def safe_failure() -> Scenario:
    return make_scenario("safe_failure", fail_update=True)


def async_change() -> Scenario:
    return make_scenario("async_change", asynchronous=True)
