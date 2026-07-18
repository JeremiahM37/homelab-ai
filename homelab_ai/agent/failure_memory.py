"""SQLite-backed failure memory.

Prevents the agent from firing the same fix for the same recurring failure
on every scan. Each unique (module, target, error_fingerprint) becomes a
row; we remember how long ago we last attempted a fix and what tier ran.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("homelab_ai.agent.memory")

SCHEMA = """
CREATE TABLE IF NOT EXISTS failures (
    fingerprint TEXT PRIMARY KEY,
    module      TEXT NOT NULL,
    target      TEXT NOT NULL,
    error       TEXT NOT NULL,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    seen_count  INTEGER NOT NULL DEFAULT 1,
    last_tier   INTEGER,
    last_fix_at REAL,
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS idx_failures_unresolved ON failures(resolved_at)
    WHERE resolved_at IS NULL;
"""


def _fingerprint(module: str, target: str, error: str) -> str:
    h = hashlib.sha1(f"{module}|{target}|{error}".encode()).hexdigest()
    return h[:16]


class FailureMemory:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def record(self, module: str, target: str, error: str) -> dict:
        """Record a failure. Returns the row with seen_count, last_fix_at, etc."""
        fp = _fingerprint(module, target, error)
        now = time.time()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO failures (fingerprint, module, target, error, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    seen_count = seen_count + 1,
                    resolved_at = NULL
                """,
                (fp, module, target, error[:500], now, now),
            )
        return dict(self.conn.execute(
            "SELECT * FROM failures WHERE fingerprint = ?", (fp,)
        ).fetchone())

    def mark_fix_attempt(self, fingerprint: str, tier: int) -> None:
        """Record that a fix at `tier` was just attempted for this failure."""
        with self.conn:
            self.conn.execute(
                "UPDATE failures SET last_tier = ?, last_fix_at = ? WHERE fingerprint = ?",
                (tier, time.time(), fingerprint),
            )

    def mark_resolved(self, fingerprint: str) -> None:
        """Mark a failure as no longer occurring."""
        with self.conn:
            self.conn.execute(
                "UPDATE failures SET resolved_at = ? WHERE fingerprint = ?",
                (time.time(), fingerprint),
            )

    def should_skip(self, fingerprint: str, cooldown_seconds: int = 300) -> bool:
        """Don't re-fix something we just touched within the cooldown."""
        row = self.conn.execute(
            "SELECT last_fix_at FROM failures WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if not row or not row["last_fix_at"]:
            return False
        return (time.time() - row["last_fix_at"]) < cooldown_seconds

    def open_failures(self) -> list[dict]:
        """Unresolved failures, most recently seen first (capped at 200)."""
        rows = self.conn.execute(
            "SELECT * FROM failures WHERE resolved_at IS NULL ORDER BY last_seen DESC LIMIT 200"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()
