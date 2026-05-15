"""Shell-command service — turn arbitrary shell commands into AI tools.

Lets advanced users plug in things that don't have a Python API. Defined
in config:

  services:
    command:
      commands:
        - name: list_files
          description: List the user's home directory.
          shell: "ls -la ~"
        - name: ping_google
          description: Ping google.com once and return the result.
          shell: "ping -c 1 google.com"

Each command must have a stable shell string — no LLM-substituted variables
(prevents injection). For dynamic args, write a small Python tool plugin.
"""
from __future__ import annotations

import asyncio
import logging

from .base import Service, ToolSpec

logger = logging.getLogger("homelab_ai.services.command")


class CommandService(Service):
    name = "command"

    async def health(self) -> dict:
        return {"ok": True, "commands": len(self.config.get("commands") or [])}

    async def restart(self) -> dict:
        return {"ok": False, "detail": "command service has no restart action"}

    def _run_factory(self, shell: str):
        async def _runner() -> dict:
            timeout = int(self.config.get("timeout_seconds", 30))
            try:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/sh", "-c", shell,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                return {"error": "timed out", "timeout": timeout}
            except Exception as e:
                return {"error": str(e)[:200]}
            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[:4000],
                "stderr": stderr.decode("utf-8", errors="replace")[:1000],
            }
        return _runner

    def tools(self) -> list[ToolSpec]:
        out = []
        for spec in self.config.get("commands") or []:
            if not isinstance(spec, dict):
                continue
            name = spec.get("name")
            shell = spec.get("shell")
            desc = spec.get("description", f"Run: {shell}")
            if not name or not shell:
                logger.warning("command tool missing name or shell: %r", spec)
                continue
            # Validate that this is a stable string, not a template.
            if "{" in shell:
                logger.warning("command %s contains '{' — refusing (no templating allowed)", name)
                continue
            out.append(ToolSpec(
                name=f"command_{name}",
                description=desc,
                handler=self._run_factory(shell),
            ))
        return out
