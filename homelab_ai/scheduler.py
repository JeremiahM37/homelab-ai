"""Cron-style scheduled tool execution — opt-in feature.

Each schedule entry looks like:

  features:
    scheduler:
      enabled: true
      schedules:
        - name: morning_briefing
          cron: "0 7 * * *"           # crontab expression
          tool: sonarr_calendar       # tool from the AI catalog
          args: {days: 1}
          notify: discord              # optional — send the result via the notifier

The scheduler runs in the FastAPI app as an asyncio task. Requires
`pip install homelab-ai[scheduler]` (croniter) for cron parsing. Without
the extra a clear error is logged at startup and no schedules fire.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homelab_ai.config import Config
    from homelab_ai.features import SchedulerFeature
    from homelab_ai.notifications.notifier import Notifier
    from homelab_ai.services.base import Service

logger = logging.getLogger("homelab_ai.scheduler")


def _gather_tools(services: dict[str, "Service"]) -> dict[str, Any]:
    out = {}
    for svc in services.values():
        for spec in svc.tools():
            out[spec.name] = spec
    return out


async def run_scheduler(
    cfg: "Config",
    feature: "SchedulerFeature",
    services: dict[str, "Service"],
    notifier: "Notifier | None" = None,
):
    """Long-running async task — wakes up each scheduled second."""
    try:
        from croniter import croniter
    except ImportError:
        logger.error(
            "features.scheduler is enabled but `croniter` is not installed. "
            "Run: pip install homelab-ai[scheduler]"
        )
        return

    import time

    tools = _gather_tools(services)
    if not feature.schedules:
        return

    # Pre-compute the next-fire time for each schedule.
    schedules = []
    now = time.time()
    for s in feature.schedules:
        try:
            it = croniter(s["cron"], now)
            schedules.append({"cfg": s, "iter": it, "next": it.get_next(float)})
        except Exception as e:
            logger.warning("scheduler: bad cron in %r: %s", s.get("name"), e)
    if not schedules:
        return

    logger.info("scheduler started with %d active schedule(s)", len(schedules))

    while True:
        now = time.time()
        next_fire = min(s["next"] for s in schedules)
        await asyncio.sleep(max(0.5, next_fire - now))
        now = time.time()
        for s in schedules:
            if s["next"] > now:
                continue
            await _fire_one(s["cfg"], tools, notifier)
            s["next"] = s["iter"].get_next(float)


async def _fire_one(schedule: dict, tools: dict, notifier) -> None:
    name = schedule.get("name") or schedule.get("tool")
    tool_name = schedule.get("tool")
    args = schedule.get("args") or {}
    spec = tools.get(tool_name)
    if not spec:
        logger.warning("scheduler: unknown tool %r in schedule %r", tool_name, name)
        return
    try:
        result = await spec.handler(**args)
        logger.info("scheduler ran %s → %s", name, _short(result))
    except Exception as e:
        logger.warning("scheduler %s failed: %s", name, e)
        result = {"error": str(e)}

    # If the schedule has notify: <channel>, push the result through the
    # notifier as an INFO-severity finding.
    if schedule.get("notify") and notifier:
        from homelab_ai.agent.modules.base import Finding, Severity
        f = Finding(
            module="scheduler",
            target=name,
            severity=Severity.INFO,
            message=f"{tool_name} → {_short(result)}",
            context={"schedule": name, "tool": tool_name, "result": result},
        )
        await notifier.publish(f, action_taken="scheduled")


def _short(x: Any, n: int = 300) -> str:
    s = str(x)
    return s if len(s) <= n else s[:n] + "…"
