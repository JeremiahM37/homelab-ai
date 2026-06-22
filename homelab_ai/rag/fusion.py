"""Hybrid-search building blocks: tokenization, BM25 keyword index, and
reciprocal-rank fusion. rank_bm25 is optional — without it, BM25 is a no-op and
retrieval degrades cleanly to dense-only.
"""
from __future__ import annotations

import re
from collections.abc import Callable

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def rrf(*ranked_lists: list[dict], k: int = 60) -> list[dict]:
    """Fuse ranked result lists by Reciprocal Rank Fusion. Each item must have
    a unique 'id'. Items appearing high in multiple lists rank highest."""
    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for lst in ranked_lists:
        for rank, hit in enumerate(lst):
            cid = hit["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            rows.setdefault(cid, hit)
    return [rows[c] for c in sorted(scores, key=lambda c: scores[c], reverse=True)]


class BM25Index:
    """In-memory BM25 over a list of {id, text, metadata} rows. Rebuilt when the
    fingerprint (e.g. chunk count) changes."""

    def __init__(self) -> None:
        self._fingerprint: object = None
        self._ids: list[str] = []
        self._rows: dict[str, dict] = {}
        self._bm = None

    @property
    def available(self) -> bool:
        return self._bm is not None

    def build(self, rows: list[dict], fingerprint: object) -> bool:
        if fingerprint == self._fingerprint and self._bm is not None:
            return True
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            self._bm = None
            return False
        self._ids = [r["id"] for r in rows]
        self._rows = {r["id"]: r for r in rows}
        self._bm = BM25Okapi([tokenize(r["text"]) for r in rows]) if rows else None
        self._fingerprint = fingerprint
        return self._bm is not None

    def search(self, query: str, k: int,
               allow: Callable[[dict], bool] | None = None) -> list[dict]:
        if not self._bm:
            return []
        scores = self._bm.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            row = self._rows[self._ids[i]]
            if allow and not allow(row.get("metadata") or {}):
                continue
            out.append({**row, "bm25": float(scores[i])})
            if len(out) >= k:
                break
        return out
