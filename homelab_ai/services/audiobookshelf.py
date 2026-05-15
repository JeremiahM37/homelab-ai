"""Audiobookshelf plugin — audiobook + podcast server."""
from __future__ import annotations

from .base import Service, ToolSpec


class Audiobookshelf(Service):
    name = "audiobookshelf"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if token := self.config.get("api_key") or self.config.get("token"):
            h["Authorization"] = f"Bearer {token}"
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/ping", headers=self._headers)
            return {"ok": bool(r.get("success") or r.get("ok") is not False)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def libraries(self) -> dict:
        r = await self._get("/api/libraries", headers=self._headers)
        libs = r.get("libraries", []) if isinstance(r, dict) else []
        return {"count": len(libs), "libraries": [{"id": lib.get("id"), "name": lib.get("name")} for lib in libs]}

    async def search(self, library_id: str, query: str, limit: int = 10) -> dict:
        r = await self._get(
            f"/api/libraries/{library_id}/search",
            headers=self._headers,
            params={"q": query, "limit": str(limit)},
        )
        books = r.get("book", []) if isinstance(r, dict) else []
        return {
            "count": len(books),
            "items": [
                {
                    "id": b.get("libraryItem", {}).get("id"),
                    "title": b.get("libraryItem", {}).get("media", {}).get("metadata", {}).get("title"),
                    "author": b.get("libraryItem", {}).get("media", {}).get("metadata", {}).get("authorName"),
                }
                for b in books
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="audiobookshelf_libraries",
                description="List Audiobookshelf libraries (their IDs and names).",
                handler=self.libraries,
            ),
            ToolSpec(
                name="audiobookshelf_search",
                description="Search a specific Audiobookshelf library by query.",
                handler=self.search,
                params={
                    "library_id": {"type": "string", "required": True},
                    "query": {"type": "string", "required": True},
                    "limit": {"type": "integer", "default": 10},
                },
            ),
        ]
