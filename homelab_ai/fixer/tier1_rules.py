"""Tier-1: rule-based fixes — no LLM, always safe.

Matches `Finding.fix_hint` strings to handler functions. Each handler
returns `{"ok": bool, "detail": str}`. If no rule matches, the finding is
returned to the agent for Tier-2 escalation.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homelab_ai.agent.modules import Finding
    from homelab_ai.services.base import Service

logger = logging.getLogger("homelab_ai.fixer.tier1")

Handler = Callable[["Finding", dict[str, "Service"]], Awaitable[dict]]


async def _restart_service(finding: Finding, services: dict[str, Service]) -> dict:
    svc = services.get(finding.target)
    if not svc:
        return {"ok": False, "detail": f"service {finding.target!r} not in registry"}
    return await svc.restart()


async def _restart_container(finding: Finding, services: dict[str, Service]) -> dict:
    """Generic: restart a Docker container by name via local Docker socket.

    Plumbing is intentionally minimal so the prototype stays small. Real
    deployments would call out to docker via aiohttp UnixConnector as in
    container_doctor.
    """
    import shutil
    import subprocess
    name = (finding.context or {}).get("container") or finding.target
    if not shutil.which("docker"):
        return {"ok": False, "detail": "docker CLI not available in this environment"}
    try:
        r = subprocess.run(["docker", "restart", name], capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "detail": (r.stdout + r.stderr)[:300]}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


RULES: dict[str, Handler] = {
    "restart_service": _restart_service,
    "restart_container": _restart_container,
}


async def try_fix(finding: Finding, services: dict[str, Service]) -> dict | None:
    """Return the fix result, or None if no rule matched."""
    handler = RULES.get(finding.fix_hint)
    if not handler:
        return None
    logger.info("tier-1 rule %s on %s", finding.fix_hint, finding.target)
    try:
        return await handler(finding, services)
    except Exception as e:
        logger.exception("tier-1 handler raised: %s", e)
        return {"ok": False, "detail": str(e)}
