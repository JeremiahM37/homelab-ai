"""Email / ntfy / gotify backends — connection-level test using a stub session."""
from unittest.mock import AsyncMock

import pytest

from homelab_ai.agent.modules import Finding, Severity
from homelab_ai.features import EmailFeature, GotifyFeature, NtfyFeature
from homelab_ai.notifications.backends import send_email, send_gotify, send_ntfy


def _finding():
    return Finding(module="m", target="t", severity=Severity.ERROR, message="boom")


@pytest.mark.asyncio
async def test_ntfy_skips_when_url_missing():
    cfg = NtfyFeature(enabled=True, url="")
    ok = await send_ntfy(_finding(), None, cfg, http=AsyncMock())
    assert ok is False


@pytest.mark.asyncio
async def test_ntfy_posts_with_priority_header():
    cfg = NtfyFeature(enabled=True, url="https://ntfy.sh/topic", priority="high")
    posted = {}

    class _Resp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    class _Sess:
        def post(self, url, **kw):
            posted["url"] = url
            posted["headers"] = kw.get("headers")
            return _Resp()

    ok = await send_ntfy(_finding(), "restart", cfg, http=_Sess())
    assert ok is True
    assert posted["url"] == "https://ntfy.sh/topic"
    assert posted["headers"]["Priority"] == "high"


@pytest.mark.asyncio
async def test_gotify_skips_when_token_missing():
    cfg = GotifyFeature(enabled=True, url="http://g", token="")
    ok = await send_gotify(_finding(), None, cfg, http=AsyncMock())
    assert ok is False


@pytest.mark.asyncio
async def test_gotify_sets_priority_by_severity():
    cfg = GotifyFeature(enabled=True, url="http://g", token="abc")
    posted = {}

    class _Resp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    class _Sess:
        def post(self, url, json=None, **kw):
            posted["json"] = json
            posted["url"] = url
            return _Resp()

    f = Finding(module="m", target="t", severity=Severity.CRITICAL, message="x")
    await send_gotify(f, None, cfg, http=_Sess())
    assert posted["json"]["priority"] == 10
    assert "token=abc" in posted["url"]


@pytest.mark.asyncio
async def test_email_skips_when_unconfigured():
    cfg = EmailFeature(enabled=True, smtp_host="", to_addresses=[])
    ok = await send_email(_finding(), None, cfg)
    assert ok is False
