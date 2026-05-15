"""Agent control endpoints — status, manual scan trigger."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request

from homelab_ai.agent.failure_memory import FailureMemory

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/status")
async def status(request: Request):
    cfg = request.app.state.cfg
    db_path = Path("./data/agent.db")
    if not db_path.exists():
        return {"running": cfg.agent.enabled, "open_failures": 0, "scan_interval": cfg.agent.scan_interval}
    mem = FailureMemory(db_path)
    try:
        return {
            "running": cfg.agent.enabled,
            "scan_interval": cfg.agent.scan_interval,
            "open_failures": len(mem.open_failures()),
            "recent": mem.open_failures()[:20],
        }
    finally:
        mem.close()


@router.post("/scan")
async def trigger_scan(request: Request):
    """Run a single scan in the background; return immediately."""
    cfg = request.app.state.cfg
    from homelab_ai.agent.loop import scan_once
    asyncio.create_task(scan_once(cfg))
    return {"ok": True, "detail": "scan started"}
