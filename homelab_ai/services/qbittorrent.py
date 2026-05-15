"""qBittorrent plugin — torrent client."""
from __future__ import annotations

import logging

import aiohttp

from .base import Service, ToolSpec

logger = logging.getLogger("homelab_ai.services.qbittorrent")


class QBittorrent(Service):
    name = "qbittorrent"

    def __init__(self, config: dict, http: aiohttp.ClientSession):
        super().__init__(config, http)
        self._cookie: str | None = None

    async def _login(self) -> None:
        if self._cookie:
            return
        url = self.config["url"].rstrip("/") + "/api/v2/auth/login"
        data = {
            "username": self.config.get("username", ""),
            "password": self.config.get("password", ""),
        }
        async with self.http.post(url, data=data) as r:
            r.raise_for_status()
            body = (await r.text()).strip()
            if body != "Ok.":
                raise RuntimeError(f"qBittorrent login failed: {body}")
            self._cookie = r.cookies.get("SID").value if r.cookies.get("SID") else None

    async def _api(self, path: str, **kwargs) -> dict:
        await self._login()
        url = self.config["url"].rstrip("/") + path
        headers = kwargs.pop("headers", {})
        if self._cookie:
            headers["Cookie"] = f"SID={self._cookie}"
        async with self.http.get(url, headers=headers, **kwargs) as r:
            if r.status == 403:
                self._cookie = None  # session expired — caller retries
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                return await r.json()
            return {"raw": await r.text()}

    async def health(self) -> dict:
        try:
            info = await self._api("/api/v2/app/version")
            return {"ok": True, "version": info.get("raw") or info}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def transfer_info(self) -> dict:
        return await self._api("/api/v2/transfer/info")

    async def list_torrents(self, filter: str = "all") -> dict:
        ts = await self._api("/api/v2/torrents/info", params={"filter": filter})
        # _api returns a dict; for list-returning endpoints qBit responds 200 + JSON array,
        # which our helper swallows in {"raw": ...}. Fall back to JSON if needed.
        if isinstance(ts, dict) and "raw" in ts:
            import json
            try:
                ts = json.loads(ts["raw"])
            except Exception:
                ts = []
        return {
            "count": len(ts) if isinstance(ts, list) else 0,
            "torrents": [
                {"name": t.get("name"), "state": t.get("state"), "progress": t.get("progress")}
                for t in (ts or [])[:50]
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="qbittorrent_transfer_info",
                description="Get current download/upload speeds and connection stats.",
                handler=self.transfer_info,
            ),
            ToolSpec(
                name="qbittorrent_list_torrents",
                description="List torrents on qBittorrent, optionally filtered by state.",
                handler=self.list_torrents,
                params={
                    "filter": {
                        "type": "string",
                        "description": "State filter: all, downloading, completed, paused, errored",
                        "default": "all",
                    },
                },
            ),
        ]
