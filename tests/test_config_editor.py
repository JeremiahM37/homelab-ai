"""Web config editor — schema, current (redacted), save (refuses w/o auth)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.api.routers.config_editor import _redact_secrets
from homelab_ai.auth.passwords import hash_password
from homelab_ai.config import Config


def _app(tmp_path, with_auth=True):
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg.settings.store_path = str(tmp_path / "settings.yaml")
    if with_auth:
        cfg.auth.enabled = True
        cfg.auth.api_key = "hk_test"
    cfg_yaml = tmp_path / "config.yaml"
    cfg_yaml.write_text("server:\n  port: 9105\n")
    cfg._raw = {"features": {"config_editor": {
        "enabled": True, "config_path": str(cfg_yaml),
    }}}
    return create_app(cfg)


def test_schema_returns_section_list(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        r = c.get("/api/config/schema", headers={"X-Api-Key": "hk_test"})
        assert r.status_code == 200
        names = {s["name"] for s in r.json()["sections"]}
        for must_have in ("server", "llm", "auth", "agent", "features"):
            assert must_have in names


def test_current_redacts_secrets():
    raw = {
        "llm": {"api_key": "sk-real-key", "url": "http://x"},
        "auth": {"api_key": "hk_real", "enabled": True},
        "services": {
            "sonarr": {"api_key": "secret", "url": "http://sonarr:8989"},
            "qbittorrent": {"password": "pass123", "username": "jam"},
        },
    }
    redacted = _redact_secrets(raw)
    assert redacted["llm"]["api_key"].startswith("•")
    assert redacted["llm"]["url"] == "http://x"           # not a secret
    assert redacted["auth"]["api_key"].startswith("•")
    assert redacted["auth"]["enabled"] is True             # not a secret
    assert redacted["services"]["sonarr"]["api_key"].startswith("•")
    assert redacted["services"]["sonarr"]["url"] == "http://sonarr:8989"
    assert redacted["services"]["qbittorrent"]["password"].startswith("•")
    assert redacted["services"]["qbittorrent"]["username"] == "jam"


def test_save_refuses_when_auth_disabled(tmp_path):
    """The config editor refuses writes if auth is off — otherwise it's a
    footgun for anyone with LAN access."""
    with TestClient(_app(tmp_path, with_auth=False)) as c:
        r = c.put("/api/config/save", json={"yaml": "server:\n  port: 9999\n"})
        assert r.status_code == 403


def test_save_with_invalid_yaml_rejected(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        r = c.put("/api/config/save",
                  headers={"X-Api-Key": "hk_test"},
                  json={"yaml": "key: : : invalid"})
        assert r.status_code == 400


def test_save_yaml_persists_to_disk(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        new_text = "server:\n  port: 9876\n"
        r = c.put("/api/config/save",
                  headers={"X-Api-Key": "hk_test"},
                  json={"yaml": new_text})
        assert r.status_code == 200
        assert r.json()["restart_required"] is True
        assert (tmp_path / "config.yaml").read_text() == new_text


def test_save_parsed_dict_persists(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        r = c.put("/api/config/save",
                  headers={"X-Api-Key": "hk_test"},
                  json={"parsed": {"server": {"port": 5555}}})
        assert r.status_code == 200
        out = (tmp_path / "config.yaml").read_text()
        assert "port: 5555" in out


def test_endpoint_off_means_no_route(tmp_path):
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    with TestClient(create_app(cfg)) as c:
        r = c.get("/api/config/schema")
        assert r.status_code == 404
