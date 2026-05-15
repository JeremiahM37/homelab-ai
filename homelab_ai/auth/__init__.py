"""Built-in auth — API key + optional username/password session.

If `auth.enabled` is false (the default) the middleware is a no-op and
everything is open — same as v0.2. Turn it on by setting `auth.api_key`
and/or adding users to `auth.users` in config.yaml.
"""
from .middleware import AuthMiddleware
from .passwords import hash_password, verify_password
from .sessions import SessionStore

__all__ = ["AuthMiddleware", "SessionStore", "hash_password", "verify_password"]
