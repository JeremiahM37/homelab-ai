"""SemanticToolRouter — keyword fallback + embedding mode."""
import pytest

from homelab_ai.mcp.tool_router import SemanticToolRouter

TOOLS = [
    {"name": "jellyfin_search", "description": "Search Jellyfin library by title"},
    {"name": "sonarr_calendar", "description": "Upcoming TV episodes from Sonarr"},
    {"name": "qbittorrent_list", "description": "List qBittorrent torrents"},
    {"name": "web_search", "description": "Search the public web via SearXNG"},
    {"name": "ha_get_state", "description": "Get Home Assistant entity state"},
]


@pytest.mark.asyncio
async def test_keyword_fallback_picks_relevant_tool():
    r = SemanticToolRouter(TOOLS)
    picked = await r.select("what's airing on sonarr soon?", k=2)
    names = {t["name"] for t in picked}
    assert "sonarr_calendar" in names


@pytest.mark.asyncio
async def test_keyword_no_overlap_returns_first_k():
    r = SemanticToolRouter(TOOLS)
    picked = await r.select("xyzzy plugh nothing matches", k=3)
    assert len(picked) == 3


@pytest.mark.asyncio
async def test_embedding_path_when_warmed():
    async def fake_embed(text):
        # Trivial deterministic embedding by length + 'sonarr' bias.
        base = [float(len(text))]
        if "sonarr" in text.lower():
            base.append(10.0)
        else:
            base.append(0.1)
        return base
    r = SemanticToolRouter(TOOLS, embedder=fake_embed)
    report = await r.warm_up()
    assert report["backend"] == "embedding"
    picked = await r.select("sonarr calendar please", k=2)
    assert any("sonarr" in t["name"] for t in picked)


def test_cosine_basic():
    assert SemanticToolRouter._cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert SemanticToolRouter._cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert SemanticToolRouter._cosine([], [1]) == 0.0
