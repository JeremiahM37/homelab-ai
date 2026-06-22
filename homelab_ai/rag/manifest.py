"""Incremental-indexing manifest (sqlite, stdlib only).

Records each source's content hash and chunk count so re-ingesting unchanged
content is a no-op, and a changed source can have its stale chunks pruned before
the new ones are written.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path


def content_hash(text: str, metadata: dict | None = None) -> str:
    h = hashlib.sha256()
    h.update((text or "").encode("utf-8", "ignore"))
    if metadata:
        for k in sorted(metadata):
            h.update(f"\x00{k}={metadata[k]}".encode("utf-8", "ignore"))
    return h.hexdigest()


class Manifest:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                source TEXT PRIMARY KEY,
                content_hash TEXT, n_chunks INTEGER, tier TEXT, updated_at REAL
            )""")
        self.db.commit()

    def unchanged(self, source: str, chash: str) -> bool:
        row = self.db.execute(
            "SELECT content_hash FROM sources WHERE source=?", (source,)).fetchone()
        return bool(row) and row[0] == chash

    def record(self, source: str, chash: str, n_chunks: int, tier: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?)",
            (source, chash, n_chunks, tier, time.time()))
        self.db.commit()

    def forget(self, source: str) -> None:
        self.db.execute("DELETE FROM sources WHERE source=?", (source,))
        self.db.commit()

    def n_chunks(self, source: str) -> int:
        row = self.db.execute(
            "SELECT n_chunks FROM sources WHERE source=?", (source,)).fetchone()
        return row[0] if row else 0

    def stats(self) -> dict:
        by_tier = dict(self.db.execute(
            "SELECT tier, COUNT(*) FROM sources GROUP BY tier").fetchall())
        total = self.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return {"sources": total, "sources_by_tier": by_tier}
