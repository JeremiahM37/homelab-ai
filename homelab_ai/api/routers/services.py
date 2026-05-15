"""Service inspection endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("")
async def list_services(request: Request):
    services = request.app.state.services
    return {
        "count": len(services),
        "services": list(services.keys()),
    }


@router.get("/{name}/health")
async def service_health(name: str, request: Request):
    svc = request.app.state.services.get(name)
    if not svc:
        raise HTTPException(404, f"service {name!r} not configured")
    return await svc.health()


@router.post("/{name}/restart")
async def service_restart(name: str, request: Request):
    svc = request.app.state.services.get(name)
    if not svc:
        raise HTTPException(404, f"service {name!r} not configured")
    return await svc.restart()
