"""Controller evidence survives application replay and worker termination."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE events (seq INTEGER PRIMARY KEY, kind TEXT, payload TEXT);
                CREATE TABLE attempts (identity TEXT PRIMARY KEY, number INTEGER NOT NULL);
                CREATE TABLE control (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def event(self, kind: str, **payload: Any) -> int:
        payload.update(pid=os.getpid(), time_ns=time.time_ns())
        with sqlite3.connect(self.path) as db:
            cursor = db.execute(
                "INSERT INTO events(kind,payload) VALUES (?,?)",
                (kind, json.dumps(payload, sort_keys=True)),
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def events(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            return [
                {"seq": seq, "kind": kind, **json.loads(payload)}
                for seq, kind, payload in db.execute("SELECT * FROM events ORDER BY seq")
            ]

    def next_attempt(self, identity: str) -> int:
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                """INSERT INTO attempts VALUES (?,1)
                ON CONFLICT(identity) DO UPDATE SET number=number+1 RETURNING number""",
                (identity,),
            ).fetchone()
            return int(row[0])

    def get(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
            return default if row is None else json.loads(row[0])

    def set(self, key: str, value: Any) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO control VALUES (?,?)", (key, json.dumps(value)))
