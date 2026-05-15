"""Demo mode — config build, fake services return data, CLI subcommand wires up."""
import pytest

from homelab_ai.demo import build_demo_config
from homelab_ai.demo.fake_services import (
    DEMO_SERVICES,
    DemoJellyfin,
    DemoQBittorrent,
    DemoSonarr,
)


def test_demo_config_has_auth_off_and_agent_on():
    cfg = build_demo_config()
    assert cfg.auth.enabled is False
    assert cfg.agent.enabled is True
    # Plenty of services for the dashboard.
    assert len(cfg.services) >= 5


def test_demo_config_enables_showcase_features():
    cfg = build_demo_config()
    f = cfg._raw["features"]
    assert f["history"]["enabled"] is True
    assert f["config_editor"]["enabled"] is True


def test_demo_services_registry_complete():
    for name in ("sonarr", "jellyfin", "qbittorrent", "ollama", "paperless"):
        assert name in DEMO_SERVICES


@pytest.mark.asyncio
async def test_demo_sonarr_returns_calendar():
    svc = DemoSonarr({}, None)
    r = await svc.calendar(days=7)
    assert r["count"] >= 1
    assert all("title" in item for item in r["upcoming"])


@pytest.mark.asyncio
async def test_demo_jellyfin_search_filters_query():
    svc = DemoJellyfin({}, None)
    r = await svc.search("interstellar")
    assert r["count"] == 1
    assert r["items"][0]["name"] == "Interstellar"


@pytest.mark.asyncio
async def test_demo_jellyfin_search_no_match():
    svc = DemoJellyfin({}, None)
    r = await svc.search("definitely-not-a-movie")
    assert r["count"] == 0


@pytest.mark.asyncio
async def test_demo_qbittorrent_transfer_info():
    svc = DemoQBittorrent({}, None)
    r = await svc.transfer_info()
    assert "dl_rate" in r and "up_rate" in r


@pytest.mark.asyncio
async def test_demo_services_all_expose_health():
    """Every demo service must implement health() — otherwise the dashboard
    fails silently."""
    for name, cls in DEMO_SERVICES.items():
        svc = cls({}, None)
        r = await svc.health()
        assert "ok" in r, f"{name} health() returned no 'ok' field"


@pytest.mark.asyncio
async def test_demo_services_have_at_least_one_tool():
    for name, cls in DEMO_SERVICES.items():
        svc = cls({}, None)
        assert len(svc.tools()) >= 1, f"{name} should expose at least one tool"


def test_demo_runner_patches_registry_for_demo_services():
    """After _patch_loader_for_demo runs, demo service names resolve to
    DemoXxx classes, not the real ones."""
    from homelab_ai.demo.runner import _patch_loader_for_demo
    from homelab_ai.services import registry as reg

    original = reg._resolve_plugin
    try:
        _patch_loader_for_demo()
        assert reg._resolve_plugin("sonarr") is DemoSonarr
        # Anything not in the demo set still falls through to the real lookup.
        assert reg._resolve_plugin("generic_http") is not DemoSonarr
    finally:
        reg._resolve_plugin = original
