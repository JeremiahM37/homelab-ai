"""Immich plugin — self-hosted photo backup."""
from __future__ import annotations

from .base import Service, ToolSpec


class Immich(Service):
    name = "immich"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if key := self.config.get("api_key"):
            h["x-api-key"] = key
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/server/version", headers=self._headers)
            return {"ok": True, "version": f"{r.get('major', 0)}.{r.get('minor', 0)}.{r.get('patch', 0)}"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def stats(self) -> dict:
        return await self._get("/api/server/statistics", headers=self._headers)

    async def list_albums(self) -> dict:
        r = await self._get("/api/albums", headers=self._headers)
        albums = r if isinstance(r, list) else []
        return {
            "count": len(albums),
            "albums": [
                {"id": a.get("id"), "name": a.get("albumName"), "asset_count": a.get("assetCount")}
                for a in albums
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="immich_stats",
                description="Server statistics for Immich (asset count, total size, users).",
                handler=self.stats,
            ),
            ToolSpec(
                name="immich_list_albums",
                description="List all photo albums in Immich.",
                handler=self.list_albums,
            ),
        ]
