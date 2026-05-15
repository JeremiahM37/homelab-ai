"""Config loader sanity tests."""
import os
from pathlib import Path

from homelab_ai.config import load_config


def test_loads_example_config(tmp_path: Path):
    src = Path(__file__).parent.parent / "config.example.yaml"
    dest = tmp_path / "config.yaml"
    dest.write_text(src.read_text())
    cfg = load_config(dest)
    assert cfg.server.port == 9105
    assert cfg.ollama.small_model
    assert cfg.agent.scan_interval >= 60


def test_missing_config_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg.agent.enabled is False  # falls back to safe defaults
    assert cfg.services == {}


def test_env_var_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "swordfish")
    p = tmp_path / "config.yaml"
    p.write_text("services:\n  thing:\n    api_key: ${MY_KEY}\n")
    cfg = load_config(p)
    assert cfg.services["thing"]["api_key"] == "swordfish"


def test_fixer_caps_default_present():
    cfg = load_config(Path("/tmp/never-exists-xyz.yaml"))
    assert cfg.agent.fixer.max_files_changed_per_fix >= 1
    assert cfg.agent.fixer.max_lines_changed_per_fix >= 10
