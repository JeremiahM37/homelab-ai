"""Auth endpoints — login, logout, current-user introspection."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, Request, Response

from homelab_ai.auth.passwords import verify_password
from homelab_ai.auth.sessions import COOKIE_NAME

logger = logging.getLogger("homelab_ai.api.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def status(request: Request) -> dict:
    """Whether auth is on, and who (if anyone) the caller is."""
    cfg = request.app.state.cfg.auth
    user = request.scope.get("user")
    return {
        "auth_enabled": cfg.enabled,
        "api_key_set": bool(cfg.api_key),
        "user_count": len(cfg.users),
        "current_user": user,
    }


@router.post("/login")
async def login(request: Request, body: dict = Body(...)) -> Response:
    """Validate user/pass, issue a signed session cookie."""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(400, "username + password required")
    cfg = request.app.state.cfg.auth
    stored = cfg.users.get(username)
    if not stored or not verify_password(password, stored):
        raise HTTPException(401, "invalid credentials")
    sessions = request.app.state.sessions
    token = sessions.issue(username)
    response = Response()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,   # set True if you serve over HTTPS
        max_age=7 * 24 * 3600,
        path="/",
    )
    response.headers["content-type"] = "application/json"
    import json
    response.body = json.dumps({"ok": True, "username": username}).encode()
    return response


@router.post("/logout")
async def logout() -> Response:
    """Clear the session cookie."""
    response = Response('{"ok":true}', media_type="application/json")
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
