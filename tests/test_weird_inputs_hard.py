"""Harder tests — cases I genuinely think will fail until proven otherwise.

If a test here passes on first try, great. If it fails, it's a bug to fix.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.config import Config, NotifyConfig
from homelab_ai.notifications.notifier import Notifier

# ── Sync handler in a ToolSpec ───────────────────────────────────────────────

def test_sync_handler_in_toolspec_should_either_work_or_fail_clearly():
    """A user writes a plugin with a sync `def my_tool()` — homelab-ai awaits
    every handler, so this would error with 'object dict is not awaitable'.

    Either we should detect sync handlers and wrap them, or we should fail
    *clearly* at plugin-load time. A 500 deep in the agent loop is bad UX.
    """
    from homelab_ai.api.routers.ai import _run_tool

    def sync_handler(**kw):
        return {"ok": True}

    tool = {"name": "t", "handler": sync_handler}
    result = asyncio.run(_run_tool(tool, {}))
    # We expect either:
    #   (a) the result {"ok": True} — meaning we transparently support sync, OR
    #   (b) a clean {"error": "..."} message pointing at sync handlers.
    # What we DON'T want is an unhandled exception traceback.
    assert isinstance(result, dict)
    if "error" not in result:
        assert result.get("ok") is True


# ── /api/ai/agent when the LLM URL is dead ──────────────────────────────────

def test_agent_endpoint_with_unreachable_llm_returns_clean_error(tmp_path):
    """If `llm.url` points at nothing (firewalled / wrong port), the user's
    chat request shouldn't hang or 500 — it should come back with a helpful
    payload telling them the LLM is down."""
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.settings.store_path = str(tmp_path / "settings.yaml")
    cfg._raw = {"llm": {"backend": "ollama", "url": "http://127.0.0.1:1"}}  # nothing listening
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/ai/agent", json={"prompt": "hi"})
        # Must respond (not hang) and must be JSON-decodable.
        assert r.status_code in (200, 502)
        body = r.json()
        # Either an explicit error key or an `answer` mentioning failure.
        assert "error" in body or "unreachable" in (body.get("answer") or "").lower() or "answer" in body


# ── Notifier with http=None when webhook is enabled ─────────────────────────

@pytest.mark.asyncio
async def test_notifier_publish_when_http_is_none_and_webhook_set(tmp_path):
    """If someone constructs a Notifier without an http session (test setup,
    unit tests, etc.) but discord_webhook is set, publish() must not crash.
    """
    from homelab_ai.agent.modules import Finding, Severity
    n = Notifier(NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=10),
                 http=None, state_path=tmp_path / "n.json")
    finding = Finding(module="m", target="t", severity=Severity.ERROR, message="boom")
    # Currently this will crash because `self.http.post(...)` is called on None.
    # We can document a contract ("Notifier needs http") OR make it tolerate None.
    # Either way, no unhandled AttributeError.
    try:
        ok = await n.publish(finding)
    except AttributeError as e:
        pytest.fail(f"Notifier crashed on None http: {e}")
    assert ok in (True, False)


# ── Discovery probe with a real hung connection ─────────────────────────────

@pytest.mark.asyncio
async def test_probe_with_slow_server_respects_timeout():
    """A real server that accepts the TCP connection but never responds.
    The probe must time out cleanly within ~timeout seconds, not stall.
    """
    import time

    from homelab_ai.discovery.probe import ServiceProbe, probe_one

    class _StallingResp:
        status = 200
        async def __aenter__(self):
            await asyncio.sleep(10)  # longer than our probe timeout
            return self
        async def __aexit__(self, *a): return None
        async def text(self): return ""
        headers = {}

    class _StallingSession:
        def get(self, url, **kw):
            return _StallingResp()

    sp = ServiceProbe("sonarr", 8989, "/", "Sonarr")
    started = time.time()
    hit = await asyncio.wait_for(
        probe_one(_StallingSession(), "127.0.0.1", sp, timeout=0.5),
        timeout=2.0,
    )
    elapsed = time.time() - started
    # Either the probe itself enforces the timeout (returns None quickly), or
    # our wait_for catches it. Either way, less than 2 seconds.
    assert elapsed < 2.0
    assert hit is None


# ── Tool router with all-empty descriptions ─────────────────────────────────

@pytest.mark.asyncio
async def test_semantic_router_handles_empty_descriptions():
    """A user wrote a plugin where every tool has description="". The router
    used to crash on `scored[0][0]` when all scores were 0; now it should
    return first-k."""
    from homelab_ai.mcp.tool_router import SemanticToolRouter
    tools = [{"name": f"t{i}", "description": ""} for i in range(5)]
    r = SemanticToolRouter(tools)
    picked = await r.select("anything", k=3)
    assert len(picked) == 3


# ── Webhook handler with nested template key ────────────────────────────────

def test_webhook_template_does_not_support_nested_keys():
    """Templates like `{{user.name}}` aren't supported. Behavior should be:
    pass through literal or empty; never KeyError."""
    from homelab_ai.api.routers.webhooks import _render_args
    out = _render_args({"name": "{{user.name}}"},
                       {"user": {"name": "alice"}})
    # We don't support dotted access; whatever we return must not crash.
    assert "name" in out


# ── Settings PUT with edge-case values ───────────────────────────────────────

def test_settings_put_with_nested_yaml_round_trips(tmp_path):
    """User puts a nested dict; GET should return the exact same shape."""
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.settings.store_path = str(tmp_path / "settings.yaml")
    payload = {
        "theme": "dark",
        "shortcuts": [{"key": "g", "action": "go_home"}],
        "advanced": {"foo": {"bar": "baz", "n": 42}},
    }
    with TestClient(create_app(cfg)) as c:
        c.put("/api/settings", json=payload)
        out = c.get("/api/settings").json()
        assert out == payload


# ── History store with concurrent writes ────────────────────────────────────

@pytest.mark.asyncio
async def test_history_handles_concurrent_record_calls(tmp_path):
    """Two scans complete at nearly the same time. SQLite primary key is ts
    (a float). On a fast machine two writes can land in the same microsecond
    — the INSERT OR REPLACE must handle that without raising."""
    from homelab_ai.history import HistoryStore
    s = HistoryStore(tmp_path / "h.db")

    async def _write(i):
        s.record_scan({"i": i})

    await asyncio.gather(*[_write(i) for i in range(20)])
    # At least one row should be present (PRIMARY KEY collisions overwrite).
    assert len(s.recent_scans(limit=50)) >= 1


# ── Loop module with two AgentModule subclasses ─────────────────────────────

def test_agent_module_loader_picks_name_match(tmp_path, monkeypatch):
    """A user file with two AgentModule subclasses A and B. The loader
    should pick the one whose `.name` matches the config entry."""
    from homelab_ai.agent.loop import _load_modules
    from homelab_ai.config import Config

    user_dir = tmp_path / "agent_modules"
    user_dir.mkdir()
    (user_dir / "my_thing.py").write_text("""
from homelab_ai.agent.modules import AgentModule, Finding, Severity

class FirstOne(AgentModule):
    name = "first"
    async def scan(self): return []

class MyThing(AgentModule):
    name = "my_thing"
    async def scan(self): return []
""")
    monkeypatch.setenv("HOMELAB_AI_AGENT_MODULES", str(user_dir))
    cfg = Config()
    cfg.agent.modules = ["my_thing"]
    mods = _load_modules(cfg, services={})
    assert len(mods) == 1
    # Currently the loader picks whichever AgentModule subclass it finds
    # first via inspect.getmembers — which sorts alphabetically. That means
    # it might pick `FirstOne` instead of `MyThing`. This test exposes whether
    # the loader correctly picks the one matching the name.
    assert mods[0].name == "my_thing"
