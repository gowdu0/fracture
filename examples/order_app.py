"""Synthetic order application with no Fracture dependency, licensed under repository MIT."""

import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class OrderState(TypedDict, total=False):
    operation: str
    shipment: int
    outcome: str


def prepare(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE shipments (id INTEGER PRIMARY KEY, operation TEXT NOT NULL)")


def ship(path: Path, operation: str, *, deduplicate: bool = True) -> dict:
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id FROM shipments WHERE operation=? ORDER BY id", (operation,)
        ).fetchone()
        if deduplicate and row:
            shipment = row[0]
        else:
            shipment = db.execute(
                "INSERT INTO shipments(operation) VALUES (?)", (operation,)
            ).lastrowid
    return {"effect_id": shipment, "operation": operation, "action": "ship", "parameters": {}}


def build_workflow(write, checkpointer=None):
    def dispatch(state: OrderState) -> dict:
        return {"shipment": write(state["operation"])["effect_id"]}

    def finish(state: OrderState) -> dict:
        return {"outcome": "completed"}

    graph = StateGraph(OrderState)
    graph.add_node("dispatch", dispatch)
    graph.add_node("finish", finish)
    graph.add_edge(START, "dispatch")
    graph.add_edge("dispatch", "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
