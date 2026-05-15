"""Wizard config generation — pure unit test, no I/O."""
import yaml

from homelab_ai.init_wizard import _build_config


def test_build_config_basic_shape():
    cfg = _build_config("http://localhost:11434", "ollama", "hk_test",
                        services=[])
    assert cfg["llm"]["backend"] == "ollama"
    assert cfg["llm"]["url"] == "http://localhost:11434"
    assert cfg["auth"]["api_key"] == "hk_test"
    assert cfg["auth"]["enabled"] is True
    assert cfg["agent"]["enabled"] is True
    assert "service_health" in cfg["agent"]["modules"]


def test_build_config_includes_discovered_services():
    services = [
        {"plugin": "sonarr", "host": "127.0.0.1", "port": 8989,
         "config": {"url": "http://127.0.0.1:8989", "api_key": ""}},
        {"plugin": "jellyfin", "host": "127.0.0.1", "port": 8096,
         "config": {"url": "http://127.0.0.1:8096"}},
    ]
    cfg = _build_config("http://x", "auto", "hk_x", services)
    assert "sonarr" in cfg["services"]
    assert "jellyfin" in cfg["services"]
    assert cfg["services"]["sonarr"]["url"] == "http://127.0.0.1:8989"


def test_build_config_strips_note_metadata():
    """The `_note` hint should not leak into the generated config block."""
    services = [
        {"plugin": "qbittorrent", "host": "127.0.0.1", "port": 8080,
         "config": {"url": "http://127.0.0.1:8080", "_note": "needs login"}},
    ]
    cfg = _build_config("http://x", "auto", "hk_x", services)
    assert "_note" not in cfg["services"]["qbittorrent"]


def test_build_config_is_yaml_serializable():
    """The wizard writes the result with yaml.safe_dump — that must round-trip."""
    cfg = _build_config("http://localhost:11434", "ollama", "hk_z",
                        services=[{
                            "plugin": "sonarr", "host": "127.0.0.1", "port": 8989,
                            "config": {"url": "http://127.0.0.1:8989", "api_key": ""},
                        }])
    text = yaml.safe_dump(cfg, sort_keys=False)
    reloaded = yaml.safe_load(text)
    assert reloaded["llm"]["url"] == "http://localhost:11434"
    assert reloaded["services"]["sonarr"]["url"] == "http://127.0.0.1:8989"
