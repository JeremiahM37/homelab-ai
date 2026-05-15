"""Password hashing — bcrypt via Python's `bcrypt` package if installed,
PBKDF2-SHA256 (stdlib) as a fallback.

The PBKDF2 fallback uses 600,000 iterations (OWASP 2023 minimum). bcrypt
is preferred but adding `bcrypt` to required deps is annoying for users
who don't enable auth — so we degrade gracefully.

Format on disk:
  bcrypt:    "$2b$12$..."        (verified with bcrypt.checkpw)
  pbkdf2:    "pbkdf2_sha256$600000$<b64-salt>$<b64-hash>"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

try:
    import bcrypt  # type: ignore
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False


PBKDF2_ITER = 600_000


def hash_password(password: str) -> str:
    if _HAS_BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("$2"):
        if not _HAS_BCRYPT:
            return False
        try:
            return bcrypt.checkpw(password.encode(), stored.encode())
        except Exception:
            return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iter_s, salt_b64, hash_b64 = stored.split("$")
            iterations = int(iter_s)
            salt = _ub64(salt_b64)
            expected = _ub64(hash_b64)
        except Exception:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return hmac.compare_digest(dk, expected)
    return False


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _ub64(s: str) -> bytes:
    return base64.b64decode(s)


def generate_api_key() -> str:
    """Random URL-safe key — `hk_<32-char-token>`. Prefix makes it greppable
    if it ever leaks into a log."""
    return "hk_" + secrets.token_urlsafe(32)
