"""Optional LLM reranker. Given a query and candidate passages, asks a small
model to order them by relevance. Used after fusion to sharpen the final top-k.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable

logger = logging.getLogger("homelab_ai.rag")

# A reranker takes (query, passages, k) and returns ranked passage indices.
Reranker = Callable[[str, list[str], int], Awaitable[list[int]]]

_POOL = 12  # max candidates handed to the model


def _content(resp) -> str:
    if isinstance(resp, dict):
        if "message" in resp:
            return (resp.get("message") or {}).get("content", "") or ""
        if resp.get("choices"):
            return resp["choices"][0].get("message", {}).get("content", "") or ""
    return ""


def make_llm_reranker(client, model: str) -> Reranker:
    async def rerank(query: str, passages: list[str], k: int) -> list[int]:
        pool = passages[:_POOL]
        if len(pool) <= k:
            return list(range(len(pool)))
        listing = "\n\n".join(f"[{i}] {p[:500]}" for i, p in enumerate(pool))
        msg = [{"role": "user", "content": (
            "Rank the passages by how well they help answer the question. "
            f"Return ONLY a JSON array of passage numbers, best first, max {k}.\n"
            f"Question: {query}\n\nPassages:\n{listing}\n\nJSON:")}]
        try:
            resp = await client.chat(model, msg, stream=False)
            m = re.search(r"\[.*?\]", _content(resp), re.S)
            idxs = json.loads(m.group(0)) if m else []
            out = [i for i in idxs if isinstance(i, int) and 0 <= i < len(pool)]
            if out:
                return out[:k]
        except Exception as e:  # noqa: BLE001
            logger.warning("rerank failed, keeping fused order: %s", e)
        return list(range(min(k, len(pool))))

    return rerank
