"""Nextcloud plugin — file sync + collaboration."""
from __future__ import annotations

import aiohttp

from .base import Service, ToolSpec


class Nextcloud(Service):
    name = "nextcloud"

    @property
    def _auth(self) -> aiohttp.BasicAuth | None:
        if (u := self.config.get("username")) and (p := self.config.get("app_password") or self.config.get("password")):
            return aiohttp.BasicAuth(u, p)
        return None

    async def health(self) -> dict:
        try:
            url = self.config["url"].rstrip("/") + "/status.php"
            async with self.http.get(url) as r:
                r.raise_for_status()
                data = await r.json()
            return {"ok": data.get("installed", False) and not data.get("maintenance", False),
                    "version": data.get("versionstring")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def quota(self) -> dict:
        u = self.config.get("username")
        if not u or not self._auth:
            return {"error": "username + app_password required"}
        url = self.config["url"].rstrip("/") + f"/ocs/v1.php/cloud/users/{u}"
        async with self.http.get(url, auth=self._auth, headers={"OCS-APIREQUEST": "true",
                                                                 "Accept": "application/json"}) as r:
            r.raise_for_status()
            data = await r.json()
        user = ((data.get("ocs") or {}).get("data") or {})
        q = user.get("quota") or {}
        return {
            "free_bytes": q.get("free"),
            "used_bytes": q.get("used"),
            "total_bytes": q.get("total"),
            "relative_pct": q.get("relative"),
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="nextcloud_quota",
                description="Get Nextcloud storage usage for the configured user.",
                handler=self.quota,
            ),
        ]
