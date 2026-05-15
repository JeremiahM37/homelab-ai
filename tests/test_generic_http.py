"""Declarative generic_http plugin — auth, path templating, response shaping."""
import pytest

from homelab_ai.services.generic_http import (
    GenericHTTP,
    _dot_extract,
    _format_path,
    _format_template,
)

# ── helpers ──────────────────────────────────────────────────────────────────

def test_format_path_simple_substitution():
    assert _format_path("/things/{id}", {"id": "42"}) == "/things/42"


def test_format_path_url_encodes_segments():
    """A slash or space in an arg must not break out of its path segment."""
    out = _format_path("/things/{id}", {"id": "a/b c"})
    assert "/" not in out.replace("/things/", "")  # everything after /things/ is encoded
    assert "%2F" in out
    assert "%20" in out


def test_format_path_unfilled_placeholder_raises():
    with pytest.raises(KeyError):
        _format_path("/x/{missing}", {})


def test_format_path_with_no_templates_passes_through():
    assert _format_path("/static/path", {}) == "/static/path"


def test_format_template_nested_dict():
    out = _format_template({"a": "{x}", "b": {"c": "{y}"}}, {"x": "1", "y": "2"})
    assert out == {"a": "1", "b": {"c": "2"}}


def test_dot_extract_walks_nested_paths():
    obj = {"data": {"items": [{"name": "alice"}, {"name": "bob"}]}}
    assert _dot_extract(obj, "data.items.0.name") == "alice"
    assert _dot_extract(obj, "data.items.1.name") == "bob"


def test_dot_extract_missing_key_returns_none():
    assert _dot_extract({"a": 1}, "b.c") is None


def test_dot_extract_empty_path_returns_object():
    assert _dot_extract({"x": 1}, "") == {"x": 1}


# ── auth shapes ──────────────────────────────────────────────────────────────

def test_auth_bearer_sets_authorization_header():
    svc = GenericHTTP({"url": "http://x", "auth": {"type": "bearer", "key": "sk-x"}}, None)
    h = svc._auth_headers()
    assert h["Authorization"] == "Bearer sk-x"


def test_auth_header_uses_custom_name():
    svc = GenericHTTP({"url": "http://x", "auth": {
        "type": "header", "header_name": "X-Custom", "value": "abc",
    }}, None)
    h = svc._auth_headers()
    assert h["X-Custom"] == "abc"


def test_auth_basic_yields_basic_auth_object():
    svc = GenericHTTP({"url": "http://x", "auth": {
        "type": "basic", "username": "u", "password": "p",
    }}, None)
    assert svc._auth_basic() is not None


def test_auth_query_returns_param_dict():
    svc = GenericHTTP({"url": "http://x", "auth": {
        "type": "query", "query_name": "apikey", "value": "k",
    }}, None)
    assert svc._auth_query() == {"apikey": "k"}


def test_auth_none_adds_nothing():
    svc = GenericHTTP({"url": "http://x"}, None)
    assert svc._auth_headers() == {}
    assert svc._auth_basic() is None
    assert svc._auth_query() == {}


# ── end-to-end with fake session ─────────────────────────────────────────────

class _Resp:
    def __init__(self, status=200, json_body=None, text=""):
        self.status = status
        self._json = json_body
        self._text = text
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def text(self):
        import json
        if self._text:
            return self._text
        return json.dumps(self._json) if self._json is not None else ""


class _Session:
    def __init__(self):
        self.calls = []
        self.responses = {}    # (method, path-suffix) -> _Resp

    def stub(self, method, suffix, resp):
        self.responses[(method.upper(), suffix)] = resp

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method.upper(), "url": url, **kwargs})
        for (m, suf), resp in self.responses.items():
            if m == method.upper() and url.endswith(suf):
                return resp
        return _Resp(status=404, text="not stubbed")


@pytest.mark.asyncio
async def test_health_is_ok_when_status_lt_400():
    s = _Session()
    s.stub("GET", "/healthz", _Resp(status=200, text="ok"))
    svc = GenericHTTP({
        "url": "http://x", "health": {"path": "/healthz"},
    }, s)
    r = await svc.health()
    assert r["ok"] is True


@pytest.mark.asyncio
async def test_health_unhealthy_when_status_high():
    s = _Session()
    s.stub("GET", "/healthz", _Resp(status=503, text=""))
    svc = GenericHTTP({"url": "http://x", "health": {"path": "/healthz"}}, s)
    r = await svc.health()
    assert r["ok"] is False
    assert r["status"] == 503


@pytest.mark.asyncio
async def test_health_with_body_contains_check():
    s = _Session()
    s.stub("GET", "/healthz", _Resp(status=200, text="status: degraded"))
    svc = GenericHTTP({
        "url": "http://x",
        "health": {"path": "/healthz", "ok_if": {"body_contains": "ok"}},
    }, s)
    r = await svc.health()
    assert r["ok"] is False


@pytest.mark.asyncio
async def test_tool_runs_get_with_query_args():
    s = _Session()
    s.stub("GET", "/api/things", _Resp(status=200, json_body={"items": [{"id": 1}]}))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "list_things", "description": "d", "path": "/api/things",
        "method": "GET", "params": {"limit": {"type": "integer", "default": 10}},
    }]}, s)
    tool = svc.tools()[0]
    result = await tool.handler(limit=5)
    # The GET call should have carried `limit=5` in params.
    assert s.calls[0]["params"] == {"limit": 5}
    assert result == {"items": [{"id": 1}]}


@pytest.mark.asyncio
async def test_tool_substitutes_path_params():
    s = _Session()
    s.stub("GET", "/api/things/abc", _Resp(status=200, json_body={"id": "abc"}))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "get_thing", "description": "d",
        "path": "/api/things/{id}",
        "params": {"id": {"type": "string", "required": True, "in": "path"}},
    }]}, s)
    tool = svc.tools()[0]
    result = await tool.handler(id="abc")
    assert s.calls[0]["url"].endswith("/api/things/abc")
    assert result == {"id": "abc"}


@pytest.mark.asyncio
async def test_tool_post_sends_body():
    s = _Session()
    s.stub("POST", "/api/things", _Resp(status=201, json_body={"id": 1}))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "create_thing", "description": "d", "path": "/api/things",
        "method": "POST",
        "params": {"name": {"type": "string", "required": True, "in": "body"}},
    }]}, s)
    result = await svc.tools()[0].handler(name="alice")
    assert s.calls[0]["json"] == {"name": "alice"}
    assert result == {"id": 1}


@pytest.mark.asyncio
async def test_tool_missing_required_arg_returns_error():
    s = _Session()
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "get_thing", "description": "d", "path": "/api/things/{id}",
        "params": {"id": {"type": "string", "required": True, "in": "path"}},
    }]}, s)
    result = await svc.tools()[0].handler()  # no args
    assert "error" in result
    assert "missing required" in result["error"]


@pytest.mark.asyncio
async def test_tool_response_extract_with_dot_path():
    s = _Session()
    s.stub("GET", "/api/x", _Resp(status=200, json_body={
        "data": {"items": [{"id": 42, "name": "thing"}]},
    }))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "first_name", "description": "d", "path": "/api/x", "method": "GET",
        "response": {"extract": "data.items.0.name"},
    }]}, s)
    result = await svc.tools()[0].handler()
    assert result == {"result": "thing"}


@pytest.mark.asyncio
async def test_tool_with_http_error_status_returns_error():
    s = _Session()
    s.stub("GET", "/api/x", _Resp(status=500, json_body={"error": "boom"}))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "t", "description": "d", "path": "/api/x", "method": "GET",
    }]}, s)
    result = await svc.tools()[0].handler()
    assert result["error"].startswith("HTTP 500")


@pytest.mark.asyncio
async def test_tool_default_value_used_when_arg_missing():
    s = _Session()
    s.stub("GET", "/api/x", _Resp(status=200, json_body={"got": "ok"}))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "t", "description": "d", "path": "/api/x", "method": "GET",
        "params": {"limit": {"type": "integer", "default": 7}},
    }]}, s)
    await svc.tools()[0].handler()
    assert s.calls[0]["params"] == {"limit": 7}


@pytest.mark.asyncio
async def test_tool_routes_args_to_correct_locations():
    """Confirm in: path|query|body|header all wire to the right place."""
    s = _Session()
    s.stub("POST", "/api/things/abc", _Resp(status=200, json_body={"ok": True}))
    svc = GenericHTTP({"url": "http://x", "tools": [{
        "name": "complex", "description": "d", "path": "/api/things/{id}",
        "method": "POST",
        "params": {
            "id": {"type": "string", "required": True, "in": "path"},
            "limit": {"type": "integer", "default": 10, "in": "query"},
            "name": {"type": "string", "required": True, "in": "body"},
            "trace_id": {"type": "string", "in": "header"},
        },
    }]}, s)
    await svc.tools()[0].handler(id="abc", name="alice", trace_id="t-1")
    call = s.calls[0]
    assert call["url"].endswith("/api/things/abc")
    assert call["params"] == {"limit": 10}
    assert call["json"] == {"name": "alice"}
    assert call["headers"]["trace_id"] == "t-1"


@pytest.mark.asyncio
async def test_invalid_tool_def_skipped_silently():
    """A tool missing `name` or `path` is logged but doesn't break loading."""
    svc = GenericHTTP({"url": "http://x", "tools": [
        {"description": "no name"},
        {"name": "no_path"},
        {"name": "ok", "path": "/x"},
    ]}, None)
    out = svc.tools()
    assert len(out) == 1
    assert out[0].name == "ok"


# ── registry integration: `plugin: generic_http` in config ──────────────────

def test_registry_resolves_explicit_plugin_key(tmp_path):
    """`services.my_thing.plugin: generic_http` should load GenericHTTP."""
    from homelab_ai.services.registry import _resolve_plugin
    cls = _resolve_plugin("generic_http")
    assert cls is GenericHTTP


@pytest.mark.asyncio
async def test_registry_loads_generic_http_for_custom_name():
    """End-to-end: a user-named service routed through generic_http."""
    import aiohttp

    from homelab_ai.config import Config
    from homelab_ai.services.registry import load_services

    cfg = Config()
    cfg.services = {
        "my_unknown_thing": {
            "plugin": "generic_http",
            "url": "http://example",
            "tools": [{"name": "t", "description": "d", "path": "/x"}],
        }
    }
    async with aiohttp.ClientSession() as http:
        svcs = load_services(cfg, http)
    assert "my_unknown_thing" in svcs
    assert isinstance(svcs["my_unknown_thing"], GenericHTTP)
    assert svcs["my_unknown_thing"].tools()[0].name == "t"
