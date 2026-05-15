"""AdGuard Home plugin — DNS-level ad / tracker blocking."""
from __future__ import annotations

import aiohttp

from .base import Service, ToolSpec


class AdGuardHome(Service):
    name = "adguard"

    @property
    def _auth(self) -> aiohttp.BasicAuth | None:
        if (u := self.config.get("username")) and (p := self.config.get("password")):
            return aiohttp.BasicAuth(u, p)
        return None

    async def _get_auth(self, path: str) -> dict:
        url = self.config["url"].rstrip("/") + path
        async with self.http.get(url, auth=self._auth) as r:
            r.raise_for_status()
            return await r.json()

    async def health(self) -> dict:
        try:
            r = await self._get_auth("/control/status")
            return {"ok": bool(r.get("running")), "version": r.get("version"),
                    "protection_enabled": r.get("protection_enabled")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def stats(self) -> dict:
        r = await self._get_auth("/control/stats")
        return {
            "queries_today": r.get("num_dns_queries"),
            "blocked_today": r.get("num_blocked_filtering"),
            "block_percent": round(
                100 * (r.get("num_blocked_filtering") or 0) / max(r.get("num_dns_queries") or 1, 1),
                1,
            ),
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="adguard_stats",
                description="Get AdGuard Home stats (queries today, blocked today, block percentage).",
                handler=self.stats,
            ),
        ]
