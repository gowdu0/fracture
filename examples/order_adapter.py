"""Public API adapter; fixture, commit evidence and recovery policy are explicit."""

import sqlite3
from dataclasses import dataclass
from functools import partial

from fracture import LangGraphDriver, Scenario, action, observe_commit
from fracture.assertions import effect_count, terminal_outcome
from fracture.types import FAULTS

from . import order_app


@dataclass(frozen=True)
class OrderFixture:
    def prepare(self, directory):
        order_app.prepare(directory / "business.sqlite")

    def inspect(self, directory):
        with sqlite3.connect(directory / "business.sqlite") as db:
            rows = db.execute("SELECT id, operation FROM shipments ORDER BY id").fetchall()
        return {
            "effects": [
                {"id": i, "operation": op, "action": "ship", "parameters": {}} for i, op in rows
            ]
        }

    def describe(self):
        return {"type": "synthetic-orders", "fixture_version": 1, "initial_shipments": []}

    def supports(self, site, fault):
        return site == "ship" and fault in FAULTS

    def verify_commit(self, directory, receipt):
        with sqlite3.connect(directory / "business.sqlite") as db:
            row = db.execute(
                "SELECT operation FROM shipments WHERE id=?", (receipt.get("effect_id"),)
            ).fetchone()
        return (
            row == (receipt.get("operation"),)
            and receipt.get("action") == "ship"
            and receipt.get("parameters") == {}
        )

    def record_approval(self, directory, approval):
        raise ValueError("this fixture has no approval boundary")


def identity(operation):
    return operation, "shipment"


def workflow(context, checkpointer, *, deduplicate):
    @action("ship", identity=identity, commit_visible=True)
    def write(operation):
        receipt = order_app.ship(
            context.directory / "business.sqlite", operation, deduplicate=deduplicate
        )
        observe_commit(receipt)
        return receipt

    return order_app.build_workflow(write, checkpointer)


def make_scenario(name, deduplicate):
    return Scenario(
        name=name,
        workflow=partial(workflow, deduplicate=deduplicate),
        backend=OrderFixture(),
        driver=LangGraphDriver(error_resumes=2, restart_on_process_exit=True),
        assertions=(effect_count("order-001", "ship"), terminal_outcome("completed")),
        initial_input={"operation": "order-001"},
        source_files=(str(order_app.__file__),),
        target=f"examples.order_adapter:{name}",
    )


def corrected():
    return make_scenario("corrected", True)


def non_idempotent():
    return make_scenario("non_idempotent", False)
