"""Jellyseerr / Overseerr plugin — media request portal."""
from __future__ import annotations

from .base import Service, ToolSpec


class Jellyseerr(Service):
    name = "jellyseerr"
    api_path = "/api/v1"

    async def health(self) -> dict:
        try:
            status = await self._get(f"{self.api_path}/status", headers=self._api_headers)
            return {"ok": True, "version": status.get("version")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def search(self, query: str) -> dict:
        result = await self._get(
            f"{self.api_path}/search",
            headers=self._api_headers,
            params={"query": query},
        )
        items = result.get("results", []) if isinstance(result, dict) else []
        return {
            "count": len(items),
            "items": [
                {
                    "title": i.get("title") or i.get("name") or i.get("originalTitle"),
                    "year": (i.get("releaseDate") or i.get("firstAirDate") or "")[:4],
                    "type": i.get("mediaType"),
                    "tmdb_id": i.get("id"),
                }
                for i in items[:10]
            ],
        }

    async def requests(self, limit: int = 20) -> dict:
        result = await self._get(
            f"{self.api_path}/request",
            headers=self._api_headers,
            params={"take": str(limit)},
        )
        items = result.get("results", []) if isinstance(result, dict) else []
        return {"count": len(items), "items": items[:limit]}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="jellyseerr_search",
                description="Search Jellyseerr/Overseerr for movies and TV shows to request.",
                handler=self.search,
                params={"query": {"type": "string", "description": "Title to search", "required": True}},
            ),
            ToolSpec(
                name="jellyseerr_recent_requests",
                description="List the most recent media requests in Jellyseerr/Overseerr.",
                handler=self.requests,
                params={"limit": {"type": "integer", "description": "Max results", "default": 20}},
            ),
        ]


class Overseerr(Jellyseerr):
    name = "overseerr"
