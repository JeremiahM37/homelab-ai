"""Inbound webhooks — secret gating, template rendering, tool dispatch."""
import pytest
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.api.routers.webhooks import _render_args
from homelab_ai.config import Config


def test_render_args_substitutes_body_values():
    out = _render_args({"name": "{{user}}", "static": "x"}, {"user": "alice"})
    assert out == {"name": "alice", "static": "x"}


def test_render_args_keeps_unmatched_placeholders():
    out = _render_args({"x": "{{nope}}"}, {})
    assert out == {"x": "{{nope}}"}


def _app(receivers):
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg._raw = {"features": {"webhooks": {
        "enabled": True, "receivers": receivers,
    }}}
    return create_app(cfg)


def test_webhook_unknown_name_404():
    with TestClient(_app({})) as c:
        r = c.post("/api/webhooks/missing", json={})
        assert r.status_code == 404


def test_webhook_bad_secret_401():
    with TestClient(_app({"x": {"secret": "abc", "tool": "any"}})) as c:
        r = c.post("/api/webhooks/x?secret=wrong", json={})
        assert r.status_code == 401


def test_webhook_unknown_tool_500():
    with TestClient(_app({"x": {"secret": "", "tool": "nonexistent_tool"}})) as c:
        r = c.post("/api/webhooks/x", json={})
        assert r.status_code == 500


def test_webhook_off_means_no_route():
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/webhooks/anything", json={})
        assert r.status_code == 404   # router not even registered
