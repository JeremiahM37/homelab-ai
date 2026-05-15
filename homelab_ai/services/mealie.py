"""Mealie plugin — self-hosted recipe manager."""
from __future__ import annotations

import random

from .base import Service, ToolSpec


class Mealie(Service):
    name = "mealie"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if token := self.config.get("api_key") or self.config.get("token"):
            h["Authorization"] = f"Bearer {token}"
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/app/about", headers=self._headers)
            return {"ok": True, "version": r.get("version")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def search(self, query: str, limit: int = 10) -> dict:
        r = await self._get(
            "/api/recipes",
            headers=self._headers,
            params={"search": query, "perPage": str(limit)},
        )
        items = r.get("items", []) if isinstance(r, dict) else []
        return {
            "count": len(items),
            "recipes": [{"slug": r.get("slug"), "name": r.get("name")} for r in items],
        }

    async def random_recipe(self) -> dict:
        # Pull a small sample and pick at random.
        r = await self._get(
            "/api/recipes",
            headers=self._headers,
            params={"perPage": "50", "orderBy": "random"},
        )
        items = r.get("items", []) if isinstance(r, dict) else []
        if not items:
            return {"error": "no recipes found"}
        pick = random.choice(items)
        return {"slug": pick.get("slug"), "name": pick.get("name"), "description": pick.get("description")}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="mealie_search",
                description="Search Mealie recipes by name or text content.",
                handler=self.search,
                params={
                    "query": {"type": "string", "required": True},
                    "limit": {"type": "integer", "default": 10},
                },
            ),
            ToolSpec(
                name="mealie_random_recipe",
                description="Pick a random recipe from Mealie — useful for 'what should I cook tonight?'",
                handler=self.random_recipe,
            ),
        ]
