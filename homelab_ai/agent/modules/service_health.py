"""Hit health() on every configured service plugin and surface failures."""
from __future__ import annotations

from .base import AgentModule, Finding, Severity


class ServiceHealthModule(AgentModule):
    name = "service_health"

    async def scan(self) -> list[Finding]:
        """Call health() on every configured service; ERROR finding for each that is down."""
        findings: list[Finding] = []
        for name, svc in self.services.items():
            try:
                result = await svc.health()
            except Exception as e:
                findings.append(Finding(
                    module=self.name,
                    target=name,
                    severity=Severity.ERROR,
                    message=f"health check raised: {type(e).__name__}: {str(e)[:200]}",
                    fix_hint="restart_service",
                ))
                continue
            if not result.get("ok"):
                findings.append(Finding(
                    module=self.name,
                    target=name,
                    severity=Severity.ERROR,
                    message=result.get("error") or "health check returned ok=false",
                    fix_hint="restart_service",
                    context=result,
                ))
        return findings
