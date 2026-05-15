"""VPN watchdog — verifies a configured public-IP probe returns *some* IP.

If you torrent behind gluetun (or any VPN container), set the public-IP
URL in agent.vpn_watchdog.probe_url. The module hits it on each scan; if
the request hangs or returns a non-200 (with no public_ip field), it
surfaces a CRITICAL Finding so the torrent client gets paused / restarted
by Tier-1.
"""
from __future__ import annotations

import aiohttp

from .base import AgentModule, Finding, Severity


class VpnWatchdogModule(AgentModule):
    name = "vpn_watchdog"

    async def scan(self) -> list[Finding]:
        cfg = (self.cfg._raw.get("agent") or {}).get("vpn_watchdog") or {}
        url = cfg.get("probe_url")
        if not url:
            return []  # not configured — module is opt-in
        timeout = cfg.get("timeout_seconds", 8)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
                async with s.get(url) as r:
                    body = await r.text()
                    status = r.status
        except (TimeoutError, aiohttp.ClientError) as e:
            return [Finding(
                module=self.name, target=url, severity=Severity.CRITICAL,
                message=f"VPN probe failed: {type(e).__name__}",
                fix_hint="restart_vpn",
            )]

        # Any 2xx that mentions an IP we accept; everything else is suspicious.
        looks_alive = status < 400 and any(t in body.lower() for t in ("public_ip", "ip", "."))
        if not looks_alive:
            return [Finding(
                module=self.name, target=url, severity=Severity.CRITICAL,
                message=f"VPN probe HTTP {status} body={body[:100]!r}",
                fix_hint="restart_vpn",
            )]
        return []
