"""Jellyfin plugin — open-source media server."""
from __future__ import annotations

from .base import Service, ToolSpec


class Jellyfin(Service):
    name = "jellyfin"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if key := self.config.get("api_key"):
            h["X-Emby-Token"] = key
        return h

    async def health(self) -> dict:
        try:
            info = await self._get("/System/Info/Public", headers=self._headers)
            return {"ok": True, "version": info.get("Version"), "server": info.get("ServerName")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def now_playing(self) -> dict:
        sessions = await self._get("/Sessions", headers=self._headers)
        playing = [
            {
                "user": s.get("UserName"),
                "client": s.get("Client"),
                "item": (s.get("NowPlayingItem") or {}).get("Name"),
            }
            for s in (sessions if isinstance(sessions, list) else [])
            if s.get("NowPlayingItem")
        ]
        return {"count": len(playing), "sessions": playing}

    async def search(self, query: str, limit: int = 10) -> dict:
        params = {"searchTerm": query, "Limit": str(limit), "Recursive": "true"}
        result = await self._get("/Items", headers=self._headers, params=params)
        items = result.get("Items", []) if isinstance(result, dict) else []
        return {
            "count": len(items),
            "items": [
                {"name": i.get("Name"), "type": i.get("Type"), "year": i.get("ProductionYear")}
                for i in items
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="jellyfin_now_playing",
                description="What's currently being streamed on Jellyfin (user + title).",
                handler=self.now_playing,
            ),
            ToolSpec(
                name="jellyfin_search",
                description="Search the Jellyfin library by title and return up to N matches.",
                handler=self.search,
                params={
                    "query": {"type": "string", "description": "Search text", "required": True},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
            ),
        ]
