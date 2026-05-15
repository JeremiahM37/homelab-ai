"""Service discovery probe — signature matching + dedup."""
from unittest.mock import AsyncMock

import pytest

from homelab_ai.discovery import discover
from homelab_ai.discovery.probe import (
    KNOWN_SERVICES,
    ServiceProbe,
    probe_one,
)


class _FakeResp:
    def __init__(self, status, text="", headers=None):
        self.status = status
        self._text = text
        self.headers = headers or {}
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def text(self): return self._text


class _FakeSession:
    def __init__(self, response):
        self._response = response
    def get(self, url, **kw):
        return self._response


def test_known_services_covers_common_apps():
    plugins = {sp.plugin for sp in KNOWN_SERVICES}
    for must_have in ("sonarr", "radarr", "jellyfin", "ollama", "qbittorrent"):
        assert must_have in plugins


@pytest.mark.asyncio
async def test_probe_matches_on_body_signature():
    session = _FakeSession(_FakeResp(200, "<html>Welcome to Sonarr</html>"))
    sp = next(s for s in KNOWN_SERVICES if s.plugin == "sonarr")
    hit = await probe_one(session, "127.0.0.1", sp)
    assert hit is not None
    assert hit["plugin"] == "sonarr"
    assert hit["config"]["url"] == "http://127.0.0.1:8989"
    assert hit["config"]["api_key"] == ""   # placeholder for user


@pytest.mark.asyncio
async def test_probe_no_match_on_wrong_body():
    session = _FakeSession(_FakeResp(200, "<html>nope</html>"))
    sp = next(s for s in KNOWN_SERVICES if s.plugin == "sonarr")
    hit = await probe_one(session, "127.0.0.1", sp)
    assert hit is None


@pytest.mark.asyncio
async def test_probe_treats_connection_error_as_miss():
    class _Boom:
        def get(self, url, **kw):
            class _C:
                async def __aenter__(self): raise OSError("nope")
                async def __aexit__(self, *a): return None
            return _C()
    sp = next(s for s in KNOWN_SERVICES if s.plugin == "sonarr")
    hit = await probe_one(_Boom(), "127.0.0.1", sp)
    assert hit is None


@pytest.mark.asyncio
async def test_probe_accepts_401_as_match_for_api_key_service():
    """A 401 with no signature still indicates 'something's there'."""
    sp = ServiceProbe("foo", 8000, "/api", signature="", needs_api_key=True)
    session = _FakeSession(_FakeResp(401, ""))
    hit = await probe_one(session, "127.0.0.1", sp)
    assert hit is not None
    assert hit["config"]["api_key"] == ""


@pytest.mark.asyncio
async def test_probe_includes_note_for_unusual_services():
    sp = next(s for s in KNOWN_SERVICES if s.plugin == "qbittorrent")
    session = _FakeSession(_FakeResp(200, ""))
    hit = await probe_one(session, "127.0.0.1", sp)
    assert hit is not None
    assert "_note" in hit["config"]


@pytest.mark.asyncio
async def test_discover_returns_empty_for_no_hosts():
    out = await discover([])
    assert out == []
