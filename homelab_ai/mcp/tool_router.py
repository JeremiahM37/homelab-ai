"""Semantic tool selection.

Given a user query, pick the smallest relevant subset of tools to pass to
the LLM. Reduces prompt size and improves tool-calling accuracy when the
catalog has 50+ tools.

Strategy: embed every tool description once at startup, embed the query at
call time, return the top-k tools by cosine similarity. If no embedding
backend is available (no Ollama yet), fall back to keyword overlap.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

logger = logging.getLogger("homelab_ai.mcp.router")

WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_-]+\b")


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in WORD_RE.findall(text) if len(w) > 2}


class SemanticToolRouter:
    """Embedding-backed when an embedder is provided; keyword overlap fallback."""

    def __init__(
        self,
        tools: list[dict],
        embedder: Callable[[str], Awaitable[list[float]]] | None = None,
    ):
        self.tools = tools
        self.embedder = embedder
        self._tool_tokens = [(_tokenize(f"{t['name']} {t['description']}"), t) for t in tools]
        self._tool_embeddings: list[list[float]] | None = None

    async def warm_up(self) -> dict:
        if not self.embedder:
            return {"backend": "keyword", "tools": len(self.tools)}
        embs: list[list[float]] = []
        for t in self.tools:
            text = f"{t['name']}: {t['description']}"
            embs.append(await self.embedder(text))
        self._tool_embeddings = embs
        return {"backend": "embedding", "tools": len(self.tools)}

    async def select(self, query: str, k: int = 8) -> list[dict]:
        if self._tool_embeddings and self.embedder:
            q_emb = await self.embedder(query)
            scored = [
                (self._cosine(q_emb, e), t)
                for e, t in zip(self._tool_embeddings, self.tools, strict=False)
            ]
        else:
            q_tokens = _tokenize(query)
            scored = [
                (len(q_tokens & toks) / max(len(q_tokens) + len(toks), 1), tool)
                for toks, tool in self._tool_tokens
            ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:k]]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0
