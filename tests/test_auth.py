"""Auth — password hashing, session signing, middleware gating."""
import pytest
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.auth.passwords import (
    generate_api_key,
    hash_password,
    verify_password,
)
from homelab_ai.auth.sessions import SessionStore
from homelab_ai.config import Config


def test_password_roundtrip():
    h = hash_password("secret")
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)


def test_empty_password_fails():
    h = hash_password("secret")
    assert not verify_password("", h)


def test_password_handles_unicode():
    h = hash_password("pässw🔑rd")
    assert verify_password("pässw🔑rd", h)
    assert not verify_password("password", h)


def test_unknown_hash_format_returns_false():
    assert not verify_password("anything", "garbage")
    assert not verify_password("anything", "")


def test_generate_api_key_is_prefixed():
    k = generate_api_key()
    assert k.startswith("hk_")
    assert len(k) > 20
    assert generate_api_key() != generate_api_key()  # unique


def test_session_issue_and_verify():
    s = SessionStore("secret")
    token = s.issue("alice")
    assert s.verify(token) == "alice"


def test_session_rejects_tampering():
    s = SessionStore("secret")
    token = s.issue("alice")
    # Modify the username portion — signature should no longer match.
    parts = token.split(".")
    parts[0] = "bob"
    bad = ".".join(parts)
    assert s.verify(bad) is None


def test_session_rejects_expired():
    s = SessionStore("secret")
    token = s.issue("alice", ttl=-1)  # already expired
    assert s.verify(token) is None


def test_session_secret_change_invalidates_all():
    s1 = SessionStore("secret-a")
    token = s1.issue("alice")
    s2 = SessionStore("secret-b")
    assert s2.verify(token) is None


# ── middleware integration via TestClient ────────────────────────────────────

def _auth_app(tmp_path):
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.auth.enabled = True
    cfg.auth.api_key = "hk_testkey123"
    cfg.auth.users = {"alice": hash_password("hunter2")}
    cfg.auth.session_secret = "test-session-secret"
    cfg.settings.store_path = str(tmp_path / "settings.yaml")
    return create_app(cfg)


def test_health_is_exempt(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        assert c.get("/api/health").status_code == 200


def test_unauthenticated_request_is_blocked(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.get("/api/services")
        assert r.status_code == 401


def test_api_key_grants_access(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.get("/api/services", headers={"X-Api-Key": "hk_testkey123"})
        assert r.status_code == 200


def test_bearer_token_also_works(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.get("/api/services", headers={"Authorization": "Bearer hk_testkey123"})
        assert r.status_code == 200


def test_wrong_api_key_rejected(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.get("/api/services", headers={"X-Api-Key": "nope"})
        assert r.status_code == 401


def test_login_then_session_cookie_grants_access(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.post("/api/auth/login", json={"username": "alice", "password": "hunter2"})
        assert r.status_code == 200
        # Cookie is now stored in c.cookies; subsequent requests should pass.
        r = c.get("/api/services")
        assert r.status_code == 200


def test_login_wrong_password_rejected(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
        assert r.status_code == 401


def test_auth_status_endpoint(tmp_path):
    with TestClient(_auth_app(tmp_path)) as c:
        r = c.get("/api/auth/status", headers={"X-Api-Key": "hk_testkey123"})
        d = r.json()
        assert d["auth_enabled"] is True
        assert d["api_key_set"] is True
        assert d["user_count"] == 1
