"""Watch the *arr import queues for stuck downloads.

A 'stuck' item is one that's been in 'warning' or 'completed-pending-import'
state across multiple scans without making progress.
"""
from __future__ import annotations

from .base import AgentModule, Finding, Severity


class ImportWatchdogModule(AgentModule):
    name = "import_watchdog"

    async def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        for name, svc in self.services.items():
            # Only relevant for *arr services that expose queue_summary.
            qs = getattr(svc, "queue_summary", None)
            if not qs:
                continue
            try:
                summary = await qs()
            except Exception:
                continue
            warning = summary.get("warning", 0) if isinstance(summary, dict) else 0
            if warning > 0:
                findings.append(Finding(
                    module=self.name,
                    target=name,
                    severity=Severity.WARNING,
                    message=f"{warning} item(s) in {name} queue have warnings",
                    fix_hint="retry_imports",
                    context={"service": name, "warning_count": warning},
                ))
        return findings
