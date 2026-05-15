"""Tunnel templates exist and are well-formed."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent / "deploy" / "tunnels"


def test_top_level_readme_exists():
    assert (ROOT / "README.md").is_file()


@pytest.mark.parametrize("flavour", ["tailscale", "cloudflared"])
def test_each_flavour_has_required_files(flavour):
    d = ROOT / flavour
    assert d.is_dir()
    assert (d / "README.md").is_file()
    assert (d / "docker-compose.yml").is_file()
    assert (d / ".env.example").is_file()


@pytest.mark.parametrize("flavour", ["tailscale", "cloudflared"])
def test_docker_compose_is_valid_yaml(flavour):
    with (ROOT / flavour / "docker-compose.yml").open() as f:
        data = yaml.safe_load(f)
    assert "services" in data
    assert "homelab-ai" in data["services"]


def test_tailscale_includes_tailscaled_sidecar():
    with (ROOT / "tailscale" / "docker-compose.yml").open() as f:
        data = yaml.safe_load(f)
    assert "tailscale" in data["services"]


def test_cloudflared_includes_cloudflared_sidecar():
    with (ROOT / "cloudflared" / "docker-compose.yml").open() as f:
        data = yaml.safe_load(f)
    assert "cloudflared" in data["services"]
