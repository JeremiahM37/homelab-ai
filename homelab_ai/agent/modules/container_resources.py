"""Watch Docker container CPU / memory for runaway usage.

Flags containers that exceed configured thresholds for N consecutive scans.
State is kept in-memory (resets on restart — that's fine, the alarm just
reactivates on the next consecutive-hits run).
"""
from __future__ import annotations

import logging
from collections import defaultdict

import aiohttp

from .base import AgentModule, Finding, Severity

logger = logging.getLogger("homelab_ai.agent.container_resources")


class ContainerResourcesModule(AgentModule):
    name = "container_resources"

    DEFAULT_CPU_PCT = 200       # 200% = 2 cores' worth
    DEFAULT_MEM_GB = 4.0
    DEFAULT_CONSECUTIVE = 3

    def __init__(self, cfg, services):
        super().__init__(cfg, services)
        self._streak: dict[str, int] = defaultdict(int)

    async def _docker(self, path: str) -> list | dict | None:
        cr_cfg = (self.cfg._raw.get("agent") or {}).get("container_resources") or {}
        host = cr_cfg.get("docker_host", "unix:///var/run/docker.sock")
        connector = aiohttp.UnixConnector(path=host.replace("unix://", "")) if host.startswith("unix://") else None
        try:
            async with aiohttp.ClientSession(connector=connector) as s:
                url = (host if not host.startswith("unix://") else "http://docker") + path
                async with s.get(url) as r:
                    if r.status >= 400:
                        return None
                    return await r.json()
        except Exception as e:
            logger.debug("docker query failed: %s", e)
            return None

    async def scan(self) -> list[Finding]:
        cr_cfg = (self.cfg._raw.get("agent") or {}).get("container_resources") or {}
        cpu_threshold = cr_cfg.get("cpu_percent", self.DEFAULT_CPU_PCT)
        mem_threshold = cr_cfg.get("mem_gb", self.DEFAULT_MEM_GB)
        consecutive = cr_cfg.get("consecutive", self.DEFAULT_CONSECUTIVE)

        containers = await self._docker("/v1.41/containers/json")
        if not containers:
            return []

        findings: list[Finding] = []
        for c in containers:
            cid = c.get("Id", "")[:12]
            name = (c.get("Names") or ["?"])[0].lstrip("/")
            stats = await self._docker(f"/v1.41/containers/{cid}/stats?stream=0")
            if not stats or not isinstance(stats, dict):
                continue
            cpu_pct = _calc_cpu_percent(stats)
            mem_bytes = (stats.get("memory_stats") or {}).get("usage", 0)
            mem_gb = mem_bytes / (1024**3)
            over = (cpu_pct >= cpu_threshold) or (mem_gb >= mem_threshold)
            if over:
                self._streak[name] += 1
                if self._streak[name] >= consecutive:
                    findings.append(Finding(
                        module=self.name,
                        target=name,
                        severity=Severity.WARNING,
                        message=(
                            f"{name} sustained: cpu={cpu_pct:.0f}% mem={mem_gb:.1f}GB "
                            f"({self._streak[name]} consecutive scans)"
                        ),
                        fix_hint="restart_container",
                        context={"container": name, "cpu_percent": cpu_pct, "mem_gb": mem_gb},
                    ))
            else:
                self._streak[name] = 0
        return findings


def _calc_cpu_percent(stats: dict) -> float:
    cpu = stats.get("cpu_stats", {}) or {}
    pre = stats.get("precpu_stats", {}) or {}
    cpu_delta = (cpu.get("cpu_usage", {}).get("total_usage", 0)
                 - pre.get("cpu_usage", {}).get("total_usage", 0))
    sys_delta = (cpu.get("system_cpu_usage", 0) or 0) - (pre.get("system_cpu_usage", 0) or 0)
    online = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [1])
    if sys_delta <= 0 or cpu_delta <= 0:
        return 0.0
    return (cpu_delta / sys_delta) * online * 100.0
