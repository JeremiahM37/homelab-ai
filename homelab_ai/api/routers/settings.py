"""Settings UI endpoint — GET/PUT of the overlay settings store.

The settings store is a yaml file separate from config.yaml so users can
edit non-secret values through the UI without touching their actual config.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Body, HTTPException, Request

logger = logging.getLogger("homelab_ai.api.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])


def _store_path(request: Request) -> Path:
    return Path(request.app.state.cfg.settings.store_path)


@router.get("")
async def get_settings(request: Request):
    path = _store_path(request)
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


@router.put("")
async def put_settings(request: Request, body: dict = Body(...)):
    if not isinstance(body, dict):
        raise HTTPException(400, "expected an object")
    path = _store_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(body, sort_keys=False))
    logger.info("settings saved to %s (%d keys)", path, len(body))
    return {"ok": True, "saved": len(body)}
