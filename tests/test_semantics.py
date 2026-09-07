"""Executable LangGraph semantics spike; uses public persistence APIs only."""

import asyncio
import multiprocessing as mp
import os
import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict, total=False):
    done: bool


def count(path: Path) -> int:
    with sqlite3.connect(path) as db:
        return db.execute("select count(*) from effects").fetchone()[0]


def graph_for(checkpointer, business: Path, mode: str, barrier=None):
    def write(state):
        with sqlite3.connect(business) as db:
            db.execute("insert into effects default values")
        if mode == "approval":
            interrupt("approve")
        elif mode == "error" and count(business) == 1:
            raise TimeoutError("response lost after commit")
        elif mode == "kill":
            barrier.send({"pid": os.getpid(), "committed": count(business)})
            barrier.recv()
        return {"done": True}

    builder = StateGraph(State)
    builder.add_node("write", write)
    builder.add_edge(START, "write")
    builder.add_edge("write", END)
    return builder.compile(checkpointer=checkpointer)


def initialize(path: Path):
    with sqlite3.connect(path) as db:
        db.execute("create table effects (id integer primary key)")


def test_approval_and_error_resume(tmp_path):
    for mode in ("approval", "error"):
        business = tmp_path / f"{mode}-business.sqlite"
        initialize(business)
        with SqliteSaver.from_conn_string(str(tmp_path / f"{mode}-cp.sqlite")) as cp:
            graph = graph_for(cp, business, mode)
            config = {"configurable": {"thread_id": mode}}
            if mode == "approval":
                result = graph.invoke({}, config, durability="sync")
                assert result["__interrupt__"]
                resume = Command(resume=True)
            else:
                try:
                    graph.invoke({}, config, durability="sync")
                except TimeoutError:
                    pass
                else:
                    raise AssertionError("expected committed response loss")
                resume = None
            assert count(business) == 1
            assert graph.get_state(config).next == ("write",)
            assert graph.invoke(resume, config, durability="sync")["done"]
            assert count(business) == 2


def child(business, checkpoint, conn, resume):
    with SqliteSaver.from_conn_string(str(checkpoint)) as cp:
        graph = graph_for(cp, business, "normal" if resume else "kill", conn)
        config = {"configurable": {"thread_id": "same-logical-run"}}
        before = graph.get_state(config)
        result = graph.invoke(None if resume else {}, config, durability="sync")
        conn.send(
            {
                "pid": os.getpid(),
                "done": result["done"],
                "prior_next": before.next,
                "prior_config": before.config,
            }
        )


def test_real_kill_then_new_worker_resume(tmp_path):
    business, checkpoint = tmp_path / "app.sqlite", tmp_path / "cp.sqlite"
    initialize(business)
    ctx = mp.get_context("spawn")
    pids = []
    for resume in (False, True):
        parent, worker = ctx.Pipe()
        process = ctx.Process(target=child, args=(business, checkpoint, worker, resume))
        process.start()
        worker.close()
        try:
            assert parent.poll(30), "worker never reached barrier/result"
            evidence = parent.recv()
            pids.append(evidence["pid"])
            if not resume:
                assert evidence["committed"] == count(business) == 1
                process.kill()
                process.join(10)
                assert process.exitcode is not None and process.exitcode != 0
            else:
                assert evidence["done"]
                assert evidence["prior_next"] == ("write",)
                assert evidence["prior_config"]["configurable"]["checkpoint_id"]
                process.join(10)
                assert process.exitcode == 0
        finally:
            if process.is_alive():
                process.kill()
                process.join(10)
            parent.close()
            process.close()
    assert pids[0] != pids[1]
    assert count(business) == 2


def test_async_sqlite_approval_and_error(tmp_path):
    async def exercise():
        for mode in ("approval", "error"):
            business = tmp_path / f"async-{mode}.sqlite"
            initialize(business)
            async with AsyncSqliteSaver.from_conn_string(
                str(tmp_path / f"async-{mode}-cp.sqlite")
            ) as cp:

                async def action(state, business=business, mode=mode):
                    with sqlite3.connect(business) as db:
                        db.execute("insert into effects default values")
                    if mode == "approval":
                        interrupt("approve")
                    elif count(business) == 1:
                        raise TimeoutError("response lost")
                    return {"done": True}

                builder = StateGraph(State).add_node("write", action)
                builder.add_edge(START, "write").add_edge("write", END)
                graph = builder.compile(checkpointer=cp)
                config = {"configurable": {"thread_id": mode}}
                if mode == "approval":
                    assert (await graph.ainvoke({}, config, durability="sync"))["__interrupt__"]
                    resume = Command(resume=True)
                else:
                    try:
                        await graph.ainvoke({}, config, durability="sync")
                    except TimeoutError:
                        pass
                    else:
                        raise AssertionError("expected timeout")
                    resume = None
                assert (await graph.ainvoke(resume, config, durability="sync"))["done"]
                assert count(business) == 2

    asyncio.run(exercise())
