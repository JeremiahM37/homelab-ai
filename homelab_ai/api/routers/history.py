"""History endpoints — only registered when features.history.enabled is true."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/history", tags=["history"])


def _store(request: Request):
    s = getattr(request.app.state, "history", None)
    if s is None:
        raise HTTPException(404, "history feature is not enabled")
    return s


@router.get("/scans")
async def scans(request: Request, limit: int = 50):
    """Recent agent scan summaries."""
    return {"scans": _store(request).recent_scans(limit=limit)}


@router.get("/ai")
async def ai_calls(request: Request, limit: int = 50):
    """Recent AI agent calls."""
    return {"ai_calls": _store(request).recent_ai_calls(limit=limit)}


@router.get("/fixes")
async def fixes(request: Request, limit: int = 100):
    """Recent fix attempts."""
    return {"fixes": _store(request).recent_fixes(limit=limit)}
