"""Watch local disk usage and warn when partitions are getting full."""
from __future__ import annotations

import shutil

from .base import AgentModule, Finding, Severity


class DiskWatcherModule(AgentModule):
    name = "disk_watcher"

    # Default thresholds — overridable via cfg._raw["agent"]["disk_watcher"]
    DEFAULT_PATHS = ["/"]
    WARN_PERCENT = 85
    CRIT_PERCENT = 95

    async def scan(self) -> list[Finding]:
        """Flag watched paths whose disk usage exceeds the warn/critical thresholds."""
        agent_cfg = (self.cfg._raw.get("agent") or {}).get("disk_watcher") or {}
        paths = agent_cfg.get("paths") or self.DEFAULT_PATHS
        warn = agent_cfg.get("warn_percent", self.WARN_PERCENT)
        crit = agent_cfg.get("crit_percent", self.CRIT_PERCENT)

        findings: list[Finding] = []
        for p in paths:
            try:
                u = shutil.disk_usage(p)
            except FileNotFoundError:
                continue
            pct = (u.used / u.total) * 100 if u.total else 0
            if pct >= crit:
                sev = Severity.CRITICAL
            elif pct >= warn:
                sev = Severity.WARNING
            else:
                continue
            findings.append(Finding(
                module=self.name,
                target=p,
                severity=sev,
                message=f"{p} is {pct:.1f}% full ({u.free // (1024**3)}GB free)",
                fix_hint="cleanup_disk" if sev == Severity.CRITICAL else "",
                context={"path": p, "percent": pct, "free_gb": u.free / (1024**3)},
            ))
        return findings
