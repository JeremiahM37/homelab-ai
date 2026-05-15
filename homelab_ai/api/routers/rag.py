"""RAG endpoints — only registered when features.rag.enabled."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter(prefix="/api/rag", tags=["rag"])


def _store(request: Request):
    s = getattr(request.app.state, "rag", None)
    if s is None:
        raise HTTPException(404, "rag feature is not enabled")
    return s


@router.post("/ingest")
async def ingest(request: Request, body: dict = Body(...)):
    """Ingest a single document.

    Body: {"source": "stable-id", "text": "...", "metadata": {...}}
    """
    source = body.get("source")
    text = body.get("text") or ""
    if not source or not text:
        raise HTTPException(400, "source + text required")
    return await _store(request).ingest(source, text, body.get("metadata"))


@router.post("/search")
async def search(request: Request, body: dict = Body(...)):
    """{"query": "...", "k": 5, "source": "optional"} → list of chunks."""
    query = body.get("query") or ""
    if not query:
        raise HTTPException(400, "query required")
    return {
        "results": await _store(request).search(
            query, k=body.get("k", 5), source=body.get("source"),
        )
    }


@router.get("/stats")
async def stats(request: Request):
    return _store(request).stats()


@router.delete("/source/{source}")
async def delete_source(source: str, request: Request):
    _store(request).delete_source(source)
    return {"ok": True}
