"""Example user agent module — drop into ~/.config/homelab-ai/agent_modules/.

Demonstrates the simplest possible scan module: check a counter file each
loop, alert if it hasn't been touched in a while. Copy + adapt.
"""
import time
from pathlib import Path

from homelab_ai.agent.modules import AgentModule, Finding, Severity


class StalenessModule(AgentModule):
    name = "staleness"

    WATCH_PATH = Path("/tmp/heartbeat")
    MAX_AGE_SECONDS = 600

    async def scan(self) -> list[Finding]:
        if not self.WATCH_PATH.is_file():
            return [Finding(
                module=self.name,
                target=str(self.WATCH_PATH),
                severity=Severity.WARNING,
                message=f"heartbeat file {self.WATCH_PATH} missing",
            )]
        age = time.time() - self.WATCH_PATH.stat().st_mtime
        if age > self.MAX_AGE_SECONDS:
            return [Finding(
                module=self.name,
                target=str(self.WATCH_PATH),
                severity=Severity.ERROR,
                message=f"heartbeat file is {int(age)}s old",
            )]
        return []
