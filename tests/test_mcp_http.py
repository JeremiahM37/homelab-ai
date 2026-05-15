"""HTTP MCP server — JSON-RPC handshake + tools/list + tools/call."""
import pytest
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.config import Config


def _app():
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg._raw = {"features": {"mcp_http": {"enabled": True}}}
    return create_app(cfg)


def test_mcp_off_means_no_route():
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    with TestClient(create_app(cfg)) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r.status_code == 404


def test_mcp_initialize_returns_server_info():
    with TestClient(_app()) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r.status_code == 200
        body = r.json()
        assert body["result"]["serverInfo"]["name"] == "homelab-ai"
        assert "protocolVersion" in body["result"]


def test_mcp_tools_list_returns_array():
    with TestClient(_app()) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert r.status_code == 200
        assert isinstance(r.json()["result"]["tools"], list)


def test_mcp_call_unknown_tool():
    with TestClient(_app()) as c:
        r = c.post("/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        })
        body = r.json()
        assert body["error"]["code"] == -32601


def test_mcp_unknown_method():
    with TestClient(_app()) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "unknown"})
        assert r.json()["error"]["code"] == -32601
