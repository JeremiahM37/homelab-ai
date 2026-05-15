"""Scheduler — cron parsing, tool dispatch, missing-dep handling."""
import asyncio

import pytest

from homelab_ai.features import SchedulerFeature
from homelab_ai.scheduler import _fire_one, run_scheduler
from homelab_ai.services.base import ToolSpec


@pytest.mark.asyncio
async def test_fire_one_invokes_tool_handler():
    called = {}

    async def _handler(**kw):
        called.update(kw)
        return {"ok": True}

    spec = ToolSpec(name="t", description="d", handler=_handler)
    await _fire_one(
        {"name": "morning", "tool": "t", "args": {"x": 1}},
        tools={"t": spec},
        notifier=None,
    )
    assert called == {"x": 1}


@pytest.mark.asyncio
async def test_fire_one_unknown_tool_is_no_op():
    """Should log a warning and not crash."""
    await _fire_one({"tool": "nope"}, tools={}, notifier=None)


@pytest.mark.asyncio
async def test_run_scheduler_with_no_schedules_returns_immediately():
    cfg_obj = type("Cfg", (), {})()
    feature = SchedulerFeature(enabled=True, schedules=[])
    await asyncio.wait_for(run_scheduler(cfg_obj, feature, {}, None), timeout=2.0)
