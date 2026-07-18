"""ASGI middleware that gates every request unless explicitly exempt.

A request passes if any of:
- auth.enabled is false (no-op)
- the path is in auth.exempt_paths (or a prefix match for /static/)
- an X-Api-Key / Authorization: Bearer header matches auth.api_key
- a signed session cookie names a known user

Otherwise the response is 401 (HTML for browser-ish requests, JSON for API).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .sessions import COOKIE_NAME, SessionStore

if TYPE_CHECKING:
    from homelab_ai.config import AuthConfig

logger = logging.getLogger("homelab_ai.auth")


def _is_exempt(path: str, exempt: list[str]) -> bool:
    """True if the path matches an exempt entry (trailing '/' = prefix match)."""
    for e in exempt:
        if e.endswith("/"):
            if path.startswith(e):
                return True
        elif path == e:
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth_cfg: "AuthConfig", sessions: SessionStore):
        super().__init__(app)
        self.cfg = auth_cfg
        self.sessions = sessions

    async def dispatch(self, request: Request, call_next):
        """Pass the request if auth is off, the path is exempt, or a key/session matches."""
        if not self.cfg.enabled:
            return await call_next(request)

        path = request.url.path
        if _is_exempt(path, self.cfg.exempt_paths):
            return await call_next(request)

        # API key — header form.
        provided = request.headers.get("x-api-key")
        if not provided:
            auth_h = request.headers.get("authorization", "")
            if auth_h.startswith("Bearer "):
                provided = auth_h[7:].strip()
        if provided and self.cfg.api_key and _safe_eq(provided, self.cfg.api_key):
            return await call_next(request)

        # Session cookie.
        cookie = request.cookies.get(COOKIE_NAME)
        if cookie and (user := self.sessions.verify(cookie)) and user in self.cfg.users:
            request.scope["user"] = user
            return await call_next(request)

        return _unauthorized(request)


def _safe_eq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


def _unauthorized(request: Request) -> Response:
    """401 response — HTML for browser requests, JSON otherwise."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return Response(
            "<html><body><h1>401 unauthorized</h1>"
            "<p>Provide an <code>X-Api-Key</code> header or log in at "
            "<a href='/login'>/login</a>.</p></body></html>",
            status_code=401, media_type="text/html",
        )
    return JSONResponse({"error": "unauthorized"}, status_code=401)
