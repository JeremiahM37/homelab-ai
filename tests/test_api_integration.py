"""FastAPI integration tests via TestClient — no real Ollama, no real services."""

import pytest
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.config import Config


@pytest.fixture
def app(tmp_path):
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.settings.store_path = str(tmp_path / "settings.yaml")
    return create_app(cfg)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_root_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "homelab-ai" in r.text


def test_services_empty(client):
    r = client.get("/api/services")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "services": []}


def test_overview_empty(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    assert r.json() == {}


def test_tool_catalog_empty(client):
    r = client.get("/api/ai/tools")
    assert r.status_code == 200
    assert r.json()["tools"] == []


def test_agent_status_when_disabled(client):
    r = client.get("/api/agent/status")
    assert r.status_code == 200
    j = r.json()
    assert j["running"] is False


def test_settings_roundtrip(client):
    # GET empty
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json() == {}
    # PUT
    r = client.put("/api/settings", json={"theme": "dark", "fav": ["a", "b"]})
    assert r.status_code == 200
    # GET back
    r = client.get("/api/settings")
    assert r.json() == {"theme": "dark", "fav": ["a", "b"]}


def test_agent_endpoint_requires_prompt(client):
    r = client.post("/api/ai/agent", json={})
    assert r.status_code == 400


def test_unknown_service_404(client):
    r = client.get("/api/services/nonexistent/health")
    assert r.status_code == 404


def test_pwa_served(client):
    r = client.get("/app")
    assert r.status_code == 200
    assert "tab-home" in r.text
    assert "tab-chat" in r.text


def test_openapi_spec(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    j = r.json()
    paths = j["paths"]
    for must_exist in ["/api/health", "/api/overview", "/api/services",
                       "/api/ai/agent", "/api/agent/status", "/api/settings"]:
        assert must_exist in paths, f"missing {must_exist} in openapi"
