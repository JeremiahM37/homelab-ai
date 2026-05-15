"""Uptime Kuma plugin — uptime monitoring.

Uptime Kuma's primary API is socket.io which is awkward over HTTP. We use
the simpler `/metrics` endpoint (Prometheus exposition format) which is
public on most installs.
"""
from __future__ import annotations

import re

from .base import Service, ToolSpec

_MONITOR_STATUS_RE = re.compile(
    r'monitor_status\{[^}]*?monitor_name="([^"]+)"[^}]*?\}\s+([0-9.]+)'
)


class UptimeKuma(Service):
    name = "uptime_kuma"

    async def health(self) -> dict:
        try:
            url = self.config["url"].rstrip("/") + "/metrics"
            headers = {}
            if token := self.config.get("api_key"):
                # Uptime Kuma uses Basic auth with empty user and API key as password.
                import base64
                headers["Authorization"] = "Basic " + base64.b64encode(f":{token}".encode()).decode()
            async with self.http.get(url, headers=headers) as r:
                if r.status != 200:
                    return {"ok": False, "error": f"HTTP {r.status} (api_key required?)"}
                await r.text()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_monitors(self) -> dict:
        url = self.config["url"].rstrip("/") + "/metrics"
        headers = {}
        if token := self.config.get("api_key"):
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(f":{token}".encode()).decode()
        async with self.http.get(url, headers=headers) as r:
            r.raise_for_status()
            text = await r.text()
        states = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}
        monitors = [
            {"name": m.group(1), "status": states.get(int(float(m.group(2))), "unknown")}
            for m in _MONITOR_STATUS_RE.finditer(text)
        ]
        return {"count": len(monitors), "monitors": monitors}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="uptime_kuma_monitors",
                description="List all monitors and their current up/down/pending status.",
                handler=self.list_monitors,
            ),
        ]
