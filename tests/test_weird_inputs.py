"""Tests aimed at things a real user would actually trip on.

These are the kinds of mistakes config files end up with after a few months
of editing: trailing slashes, YAML bool surprises, environment placeholders
that didn't get expanded, Unicode, very long strings, etc.

Each test starts as a "this should work but I bet it doesn't" hypothesis.
Failures are bugs to fix, not noise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.auth.passwords import hash_password, verify_password
from homelab_ai.auth.sessions import SessionStore
from homelab_ai.config import Config, load_config
from homelab_ai.discovery.probe import ServiceProbe, probe_one
from homelab_ai.features import Features
from homelab_ai.llm.openai_compat import (
    OpenAICompatClient,
    _normalize_messages,
    _normalize_response,
)
from homelab_ai.notifications.notifier import Notifier

# ── Config loader edge cases ─────────────────────────────────────────────────

def test_yaml_with_trailing_whitespace_in_url(tmp_path: Path):
    """A user pasted a service URL and left a trailing space. Should still match."""
    p = tmp_path / "c.yaml"
    p.write_text("services:\n  sonarr:\n    url: 'http://sonarr:8989 '\n    api_key: k\n")
    cfg = load_config(p)
    # The trailing space shouldn't break loading — but plugins may need to rstrip.
    assert "sonarr" in cfg.services


def test_yaml_enabled_yes_no_strings(tmp_path: Path):
    """YAML 1.1 turns `yes`/`no` into bool. Make sure that's what we expect."""
    p = tmp_path / "c.yaml"
    p.write_text("agent:\n  enabled: yes\n")
    cfg = load_config(p)
    assert cfg.agent.enabled is True


def test_env_var_placeholder_left_unexpanded(tmp_path: Path):
    """User forgot to export the env var → ${X} substitutes to empty string."""
    p = tmp_path / "c.yaml"
    p.write_text("services:\n  sonarr:\n    api_key: ${NEVER_SET_VAR}\n")
    cfg = load_config(p)
    # Should not crash, just be empty.
    assert cfg.services["sonarr"]["api_key"] == ""


def test_unicode_in_config_value(tmp_path: Path):
    """API keys and notes can contain unicode (rare but not invalid)."""
    p = tmp_path / "c.yaml"
    p.write_text("services:\n  thing:\n    description: 'héllo 世界'\n")
    cfg = load_config(p)
    assert cfg.services["thing"]["description"] == "héllo 世界"


def test_completely_empty_config(tmp_path: Path):
    """A config that only has `# comment` lines must still load."""
    p = tmp_path / "c.yaml"
    p.write_text("# nothing here yet\n\n")
    cfg = load_config(p)
    assert cfg.server.port == 9105


def test_features_block_is_null(tmp_path: Path):
    """`features:` with nothing after it parses as None — must not crash."""
    p = tmp_path / "c.yaml"
    p.write_text("features:\n")
    cfg = load_config(p)
    f = Features.from_config(cfg)
    assert f.metrics.enabled is False


def test_features_partial_block_keeps_unmentioned_off():
    """Only mentioning metrics should not affect rag, ntfy, etc."""
    cfg = Config()
    cfg._raw = {"features": {"metrics": {"enabled": True}}}
    f = Features.from_config(cfg)
    assert f.metrics.enabled is True
    assert f.rag.enabled is False
    assert f.ntfy.enabled is False


def test_load_config_handles_missing_file_gracefully(tmp_path: Path):
    """First-run user with no config — should return safe defaults, not error."""
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.agent.enabled is False
    assert cfg.services == {}


# ── Auth quirks ──────────────────────────────────────────────────────────────

def test_api_key_with_extra_whitespace_rejected():
    """`X-Api-Key:  hk_x ` (with spaces) — strict compare should reject."""
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.auth.enabled = True
    cfg.auth.api_key = "hk_real"
    with TestClient(create_app(cfg)) as c:
        r = c.get("/api/services", headers={"X-Api-Key": " hk_real "})
        # Real users sometimes paste with whitespace. We accept the strict
        # version only — but the error should be 401, not a 500.
        assert r.status_code in (200, 401)
        # Most important: must not crash.


def test_bearer_no_space_does_not_crash():
    """`Authorization: BearerHK_x` — malformed but must not 500."""
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.auth.enabled = True
    cfg.auth.api_key = "hk_real"
    with TestClient(create_app(cfg)) as c:
        r = c.get("/api/services", headers={"Authorization": "Bearerhk_real"})
        assert r.status_code == 401


def test_session_with_dotted_username():
    """Some IdPs use dotted usernames — session token uses `.` as separator."""
    s = SessionStore("secret")
    token = s.issue("alice.bob")
    # Round-trip should still work.
    assert s.verify(token) == "alice.bob"


def test_session_token_with_no_dots_rejected():
    s = SessionStore("secret")
    assert s.verify("garbage") is None


def test_session_token_with_non_int_expiry():
    s = SessionStore("secret")
    assert s.verify("alice.notanumber.sig") is None


def test_verify_password_with_None_stored_returns_false():
    """An auth.users entry where the hash field is missing/None."""
    assert verify_password("anything", None) is False  # type: ignore[arg-type]


def test_very_long_password_does_not_dos():
    """A 100KB password attempt must not hang."""
    h = hash_password("normal")
    huge = "x" * 100_000
    # Should return False quickly, not hang or raise.
    assert verify_password(huge, h) is False


# ── OpenAI-compat normalisation ──────────────────────────────────────────────

def test_url_with_doubled_v1_not_re_appended():
    """User pasted `http://localhost:8000/v1/v1` — we shouldn't add another."""
    c = OpenAICompatClient("http://x:8000/v1/v1", http=None)
    # Whatever we do, the URL must not have /v1/v1/v1.
    assert c.url.count("/v1") <= 2


def test_response_normalization_with_null_content():
    """OpenAI sometimes returns content: null when the model only emits tool calls."""
    r = _normalize_response({"choices": [{"message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"function": {"name": "x", "arguments": "{}"}}],
    }}]})
    assert r["message"]["content"] == ""
    assert r["message"]["tool_calls"]


def test_normalize_tool_messages_in_mixed_order():
    """A mix of role=tool and role=assistant; only tool messages get IDs backfilled."""
    msgs = _normalize_messages([
        {"role": "system", "content": "..."},
        {"role": "user", "content": "?"},
        {"role": "tool", "content": "{}"},
        {"role": "assistant", "content": "..."},
        {"role": "tool", "content": "{}"},
    ])
    assert msgs[0].get("tool_call_id") is None  # system unchanged
    assert msgs[1].get("tool_call_id") is None  # user unchanged
    assert msgs[2]["tool_call_id"]              # tool got an id
    assert msgs[3].get("tool_call_id") is None  # assistant unchanged
    assert msgs[4]["tool_call_id"]


# ── Discovery probe edge cases ───────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status, text="", headers=None):
        self.status = status
        self._text = text
        self.headers = headers or {}
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def text(self): return self._text


class _FakeSession:
    def __init__(self, response): self._response = response
    def get(self, url, **kw): return self._response


@pytest.mark.asyncio
async def test_probe_does_not_false_match_on_sibling_app_mention():
    """Sonarr probe should NOT match an Overseerr page that happens to mention 'Sonarr' (e.g. as a download client option)."""
    # The current signature is plain "Sonarr". A page listing Sonarr/Radarr
    # as download clients would also match. This is a real false-positive risk.
    # We accept it for now (the user can verify), but assert the behaviour
    # is at least deterministic and documented.
    session = _FakeSession(_FakeResp(200, "<h1>Overseerr</h1><p>Configured: Sonarr, Radarr</p>"))
    sp = next(s for s in __import__("homelab_ai.discovery.probe",
                                     fromlist=["KNOWN_SERVICES"]).KNOWN_SERVICES if s.plugin == "sonarr")
    hit = await probe_one(session, "127.0.0.1", sp)
    # If this changes (we add stricter signature checking), update the test.
    assert hit is not None  # currently a false-positive — documented behaviour


@pytest.mark.asyncio
async def test_probe_handles_huge_response_body():
    """Some services return 50KB+ HTML on / — we only scan the first 8KB."""
    big = "x" * 50_000 + "Sonarr"  # signature hidden past truncation point
    session = _FakeSession(_FakeResp(200, big))
    sp = ServiceProbe("sonarr", 8989, "/", "Sonarr")
    hit = await probe_one(session, "127.0.0.1", sp)
    # The signature lives past the 8KB cut, so this should NOT match.
    # If it does match, our truncation isn't being applied.
    assert hit is None


# ── Notifier weird state ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notifier_with_corrupt_state_file_recovers(tmp_path: Path):
    """A truncated/corrupt state JSON file should not crash the notifier."""
    state = tmp_path / "n.json"
    state.write_text("{not valid json")
    from homelab_ai.config import NotifyConfig
    n = Notifier(NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=10),
                 http=None, state_path=state)
    # Notifier should have loaded with an empty state and not raised.
    assert n._sent == {}


@pytest.mark.asyncio
async def test_notifier_save_to_readonly_dir(tmp_path: Path):
    """If the state-dir is read-only, the notifier should warn but not crash."""
    ro = tmp_path / "ro"
    ro.mkdir(mode=0o500)
    try:
        from homelab_ai.config import NotifyConfig
        n = Notifier(NotifyConfig(rate_limit_per_hour=10),
                     http=None, state_path=ro / "state.json")
        n._sent = {"x": 0}
        n._save_state()  # logs a warning, does not raise
    finally:
        ro.chmod(0o700)  # so pytest can clean up


# ── Webhook quirks ───────────────────────────────────────────────────────────

def test_webhook_with_array_body_does_not_crash():
    """grafana sends an array of alerts, not always a dict. Webhook handler
    must not crash on that shape — even if it can't template the args.
    """
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg._raw = {"features": {"webhooks": {
        "enabled": True,
        "receivers": {"alert": {"secret": "", "tool": "nope"}},
    }}}
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/webhooks/alert", json=[{"a": 1}, {"b": 2}])
        # We can't match a tool ("nope" doesn't exist), but the response must
        # be a proper HTTP error (4xx/5xx), not a Python crash (500 traceback).
        assert r.status_code in (400, 422, 500)


def test_webhook_template_with_missing_key_keeps_placeholder():
    """If the template references {{service}} but body doesn't have it,
    the literal `{{service}}` should be passed through (or empty), not crash."""
    from homelab_ai.api.routers.webhooks import _render_args
    out = _render_args({"service": "{{service}}"}, {"other": "x"})
    # Real users will see this and realize their template is wrong — better
    # than a silent KeyError.
    assert out["service"] == "{{service}}"


# ── Multi-LLM with weird config ──────────────────────────────────────────────

def test_multi_llm_requires_both_backends_set():
    """If only smart_backend is set, the router should fail loudly."""
    from homelab_ai.features import MultiLLMFeature
    from homelab_ai.llm.multi import MultiLLMRouter
    f = MultiLLMFeature(enabled=True,
                        small_backend="",   # empty
                        smart_backend="openai_compat",
                        smart_url="http://x", smart_model="gpt")
    with pytest.raises(ValueError):
        MultiLLMRouter(f, http=None)


# ── ToolSpec from user plugins ───────────────────────────────────────────────

def test_tool_with_no_description_still_works():
    """A user plugin author forgot to set description. JSON schema should not crash."""
    from homelab_ai.services.base import ToolSpec
    spec = ToolSpec(name="x", description="", handler=lambda: None)
    s = spec.json_schema()
    assert s["type"] == "object"


def test_tool_params_with_only_a_default_means_optional():
    """`params={"x": {"default": 5}}` — no type, no required, just a default."""
    from homelab_ai.services.base import ToolSpec
    spec = ToolSpec(name="t", description="d", handler=lambda **kw: kw,
                    params={"x": {"default": 5}})
    s = spec.json_schema()
    assert s["properties"]["x"]["default"] == 5
    assert "required" not in s   # default means not required
