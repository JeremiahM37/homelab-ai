"""Service plugin tests with a fake HTTP session — no live network."""
import pytest

from homelab_ai.services.arr import Prowlarr, Radarr, Sonarr
from homelab_ai.services.jellyfin import Jellyfin
from homelab_ai.services.ollama import Ollama
from homelab_ai.services.searxng import SearXNG


@pytest.mark.asyncio
async def test_sonarr_health(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v3/system/status",
                      FakeResponseFixture(json_data={"version": "4.0.0"}))
    fake_session.stub("GET", "/api/v3/health",
                      FakeResponseFixture(json_data=[]))
    svc = Sonarr({"url": "http://x:8989", "api_key": "k"}, fake_session)
    r = await svc.health()
    assert r["ok"] is True
    assert r["version"] == "4.0.0"


@pytest.mark.asyncio
async def test_sonarr_health_failure(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v3/system/status",
                      FakeResponseFixture(status=500, text_data="boom"))
    svc = Sonarr({"url": "http://x:8989", "api_key": "k"}, fake_session)
    r = await svc.health()
    assert r["ok"] is False
    assert "error" in r


@pytest.mark.asyncio
async def test_sonarr_calendar(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v3/calendar",
                      FakeResponseFixture(json_data=[
                          {"title": "S01E01", "series": {"title": "Foo"}, "airDateUtc": "2030-01-01"},
                      ]))
    svc = Sonarr({"url": "http://x:8989", "api_key": "k"}, fake_session)
    r = await svc.calendar(days=7)
    assert r["count"] == 1
    assert r["upcoming"][0]["title"] == "Foo"


@pytest.mark.asyncio
async def test_jellyfin_search(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/Items",
                      FakeResponseFixture(json_data={
                          "Items": [{"Name": "Interstellar", "Type": "Movie", "ProductionYear": 2014}]
                      }))
    svc = Jellyfin({"url": "http://x:8096", "api_key": "k"}, fake_session)
    r = await svc.search("interstellar")
    assert r["count"] == 1
    assert r["items"][0]["name"] == "Interstellar"


@pytest.mark.asyncio
async def test_ollama_models(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/tags",
                      FakeResponseFixture(json_data={
                          "models": [{"name": "qwen3.5:4b", "size": 3_400_000_000}]
                      }))
    svc = Ollama({"url": "http://x:11434"}, fake_session)
    r = await svc.list_models()
    assert r["models"][0]["size_gb"] == 3.4


@pytest.mark.asyncio
async def test_searxng_search(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/search",
                      FakeResponseFixture(json_data={
                          "results": [{"title": "T", "url": "http://x", "content": "snippet"}]
                      }))
    svc = SearXNG({"url": "http://x:8888"}, fake_session)
    r = await svc.web_search("q", limit=1)
    assert r["count"] == 1


def test_arr_tools_present():
    """Every *arr subclass should expose the standard 5 tools."""
    for cls in (Sonarr, Radarr, Prowlarr):
        svc = cls({"url": "http://x", "api_key": "k"}, None)
        names = [t.name for t in svc.tools()]
        assert f"{cls.name}_queue_summary" in names
        assert f"{cls.name}_calendar" in names
        assert f"{cls.name}_missing" in names
