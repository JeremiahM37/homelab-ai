"""Notifier — dedup, rate limit, resolved notices."""
from unittest.mock import AsyncMock

import pytest

from homelab_ai.agent.modules import Finding, Severity
from homelab_ai.config import NotifyConfig
from homelab_ai.notifications import Notifier


class _FakeContext:
    def __init__(self, status=200):
        self.status = status
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def text(self): return ""


def _http():
    s = AsyncMock()
    s.post = lambda url, **kw: _FakeContext(status=200)
    return s


def _finding(target="srv", message="boom"):
    return Finding(module="m", target=target, severity=Severity.ERROR, message=message)


@pytest.mark.asyncio
async def test_dedup_same_fingerprint_suppressed(tmp_path):
    cfg = NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=100)
    n = Notifier(cfg, _http(), state_path=tmp_path / "n.json")
    assert await n.publish(_finding()) is True
    # Second call within an hour → suppressed.
    assert await n.publish(_finding()) is False


@pytest.mark.asyncio
async def test_distinct_fingerprint_both_send(tmp_path):
    cfg = NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=100)
    n = Notifier(cfg, _http(), state_path=tmp_path / "n.json")
    assert await n.publish(_finding(target="a")) is True
    assert await n.publish(_finding(target="b")) is True


@pytest.mark.asyncio
async def test_rate_limit_enforced(tmp_path):
    cfg = NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=2)
    n = Notifier(cfg, _http(), state_path=tmp_path / "n.json")
    assert await n.publish(_finding("a")) is True
    assert await n.publish(_finding("b")) is True
    # Third unique finding within the hour — over the cap.
    assert await n.publish(_finding("c")) is False


@pytest.mark.asyncio
async def test_no_webhook_no_send(tmp_path):
    cfg = NotifyConfig(discord_webhook="", generic_webhook="", rate_limit_per_hour=10)
    n = Notifier(cfg, _http(), state_path=tmp_path / "n.json")
    assert await n.publish(_finding()) is False


@pytest.mark.asyncio
async def test_resolved_clears_dedup(tmp_path):
    cfg = NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=10)
    n = Notifier(cfg, _http(), state_path=tmp_path / "n.json")
    await n.publish(_finding())
    await n.publish_resolved(_finding())
    # After resolve, the next "broken" notice should send again.
    assert await n.publish(_finding()) is True


@pytest.mark.asyncio
async def test_state_persists(tmp_path):
    cfg = NotifyConfig(discord_webhook="http://disc", rate_limit_per_hour=10)
    path = tmp_path / "n.json"
    n1 = Notifier(cfg, _http(), state_path=path)
    await n1.publish(_finding())
    # New Notifier with same state path should reload and keep dedup.
    n2 = Notifier(cfg, _http(), state_path=path)
    assert await n2.publish(_finding()) is False
