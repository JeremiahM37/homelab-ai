"""Docker container monitor — restarts crashed containers, flags crash loops.

Requires a Docker socket. By default reads /var/run/docker.sock; set
agent.container_doctor.docker_host in config to override.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from .base import AgentModule, Finding, Severity

logger = logging.getLogger("homelab_ai.agent.container_doctor")


class ContainerDoctorModule(AgentModule):
    name = "container_doctor"

    async def _docker_get(self, path: str) -> Optional[list | dict]:
        cfg = (self.cfg._raw.get("agent") or {}).get("container_doctor") or {}
        host = cfg.get("docker_host", "unix:///var/run/docker.sock")
        connector = aiohttp.UnixConnector(path=host.replace("unix://", "")) if host.startswith("unix://") else None
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                url = (host if not host.startswith("unix://") else "http://docker") + path
                async with session.get(url) as r:
                    if r.status >= 400:
                        return None
                    return await r.json()
        except Exception as e:
            logger.debug("docker query failed: %s", e)
            return None

    async def scan(self) -> list[Finding]:
        containers = await self._docker_get("/v1.41/containers/json?all=1")
        if not containers:
            return []  # no docker, no findings

        findings: list[Finding] = []
        for c in containers:
            state = (c.get("State") or "").lower()
            status = c.get("Status") or ""
            names = [n.lstrip("/") for n in (c.get("Names") or [])]
            name = names[0] if names else c.get("Id", "?")[:12]
            if state in ("exited", "dead"):
                findings.append(Finding(
                    module=self.name,
                    target=name,
                    severity=Severity.ERROR,
                    message=f"container {name} is {state} ({status})",
                    fix_hint="restart_container",
                    context={"container": name, "state": state, "status": status},
                ))
            elif state == "restarting" and "less than a second" in status.lower():
                findings.append(Finding(
                    module=self.name,
                    target=name,
                    severity=Severity.CRITICAL,
                    message=f"container {name} is in a crash loop",
                    fix_hint="diagnose_crash_loop",
                    context={"container": name, "state": state, "status": status},
                ))
        return findings
