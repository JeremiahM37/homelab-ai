"""Transmission plugin — alternative torrent client."""
from __future__ import annotations

import aiohttp

from .base import Service, ToolSpec


class Transmission(Service):
    name = "transmission"

    def __init__(self, config: dict, http: aiohttp.ClientSession):
        super().__init__(config, http)
        self._session_id: str | None = None

    async def _rpc(self, method: str, arguments: dict | None = None) -> dict:
        url = self.config["url"].rstrip("/") + "/transmission/rpc"
        payload = {"method": method, "arguments": arguments or {}}
        auth = None
        if (u := self.config.get("username")) and (p := self.config.get("password")):
            auth = aiohttp.BasicAuth(u, p)
        for _ in range(2):  # retry once for 409 session-id
            headers = {"X-Transmission-Session-Id": self._session_id or ""}
            async with self.http.post(url, json=payload, headers=headers, auth=auth) as r:
                if r.status == 409:
                    self._session_id = r.headers.get("X-Transmission-Session-Id")
                    continue
                r.raise_for_status()
                return await r.json()
        raise RuntimeError("transmission: could not establish session-id")

    async def health(self) -> dict:
        try:
            r = await self._rpc("session-get")
            return {"ok": True, "version": (r.get("arguments") or {}).get("version")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_torrents(self) -> dict:
        r = await self._rpc("torrent-get", {"fields": ["name", "percentDone", "status", "rateDownload"]})
        ts = (r.get("arguments") or {}).get("torrents", [])
        return {
            "count": len(ts),
            "torrents": [
                {"name": t.get("name"), "progress": t.get("percentDone"), "status": t.get("status")}
                for t in ts[:50]
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="transmission_list_torrents",
                description="List Transmission torrents and their progress.",
                handler=self.list_torrents,
            ),
        ]
