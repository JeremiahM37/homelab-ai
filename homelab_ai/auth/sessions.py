"""HMAC-signed session cookies — stateless, no DB.

A session is `<username>.<expires-unix>.<hmac>`. We don't store anything;
the signature stops tampering and the timestamp stops infinite reuse.

For richer multi-device session management add a SQLite store later — for
a single-user / few-user homelab this is enough.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

SESSION_TTL = 7 * 24 * 3600  # 7 days
COOKIE_NAME = "homelab_ai_session"


class SessionStore:
    def __init__(self, secret: str):
        if not secret:
            # Auto-generate if config didn't set one. Persists for process
            # lifetime only — restart = everyone logged out, which is fine
            # for the most common deployment (one or two users).
            secret = secrets.token_urlsafe(32)
        self.secret = secret.encode()

    def issue(self, username: str, ttl: int = SESSION_TTL) -> str:
        exp = int(time.time()) + ttl
        payload = f"{username}.{exp}".encode()
        sig = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return f"{username}.{exp}.{sig}"

    def verify(self, token: str) -> str | None:
        """Return the username if valid, else None."""
        if not token or token.count(".") < 2:
            return None
        try:
            username, exp_s, sig = token.rsplit(".", 2)
            exp = int(exp_s)
        except ValueError:
            return None
        if time.time() > exp:
            return None
        payload = f"{username}.{exp}".encode()
        expected = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return username
