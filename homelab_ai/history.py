"""Optional run-history persistence.

When `features.history.enabled` is true, every agent scan, AI agent call,
and fix attempt is logged to a SQLite database. Off by default to keep the
disk footprint at zero.

Schema is tiny — three tables, all keyed by timestamp + opaque payload JSON.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("homelab_ai.history")

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    ts REAL PRIMARY KEY,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_calls (
    ts REAL PRIMARY KEY,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT,
    tool_calls_json TEXT,
    duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS fixes (
    ts REAL PRIMARY KEY,
    target TEXT NOT NULL,
    tier INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    detail TEXT
);
"""


class HistoryStore:
    def __init__(self, db_path: str | Path, keep_days: int = 30):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.keep_days = keep_days
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._prune()

    def _prune(self) -> None:
        if self.keep_days <= 0:
            return
        cutoff = time.time() - self.keep_days * 86400
        with self.conn:
            for tbl in ("scans", "ai_calls", "fixes"):
                self.conn.execute(f"DELETE FROM {tbl} WHERE ts < ?", (cutoff,))

    def record_scan(self, summary: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO scans (ts, summary) VALUES (?, ?)",
                (time.time(), json.dumps(summary, default=str)),
            )

    def record_ai_call(self, model: str, prompt: str, answer: str,
                       tool_calls: list[dict] | None, duration_ms: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO ai_calls VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), model, prompt[:8000], (answer or "")[:8000],
                 json.dumps(tool_calls or [], default=str)[:16000], duration_ms),
            )

    def record_fix(self, target: str, tier: int, outcome: str, detail: str = "") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO fixes VALUES (?, ?, ?, ?, ?)",
                (time.time(), target, tier, outcome, detail[:1000]),
            )

    def recent_scans(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scans ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"ts": r["ts"], "summary": json.loads(r["summary"])} for r in rows]

    def recent_ai_calls(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ai_calls ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "ts": r["ts"],
                "model": r["model"],
                "prompt": r["prompt"],
                "answer": r["answer"],
                "duration_ms": r["duration_ms"],
                "tool_calls": json.loads(r["tool_calls_json"] or "[]"),
            }
            for r in rows
        ]

    def recent_fixes(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM fixes ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
