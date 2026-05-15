"""Homebox plugin — home inventory tracker."""
from __future__ import annotations

import aiohttp

from .base import Service, ToolSpec


class Homebox(Service):
    name = "homebox"

    def __init__(self, config: dict, http: aiohttp.ClientSession):
        super().__init__(config, http)
        self._token: str | None = None

    async def _ensure_token(self) -> None:
        if self._token:
            return
        username = self.config.get("username")
        password = self.config.get("password")
        if not username or not password:
            raise RuntimeError("homebox: username + password required")
        url = self.config["url"].rstrip("/") + "/api/v1/users/login"
        async with self.http.post(url, json={"username": username, "password": password}) as r:
            r.raise_for_status()
            data = await r.json()
        self._token = data.get("token")

    @property
    def _h(self) -> dict:
        return {"Authorization": self._token, "Accept": "application/json"} if self._token else {}

    async def health(self) -> dict:
        try:
            await self._ensure_token()
            return {"ok": bool(self._token)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def search(self, query: str, limit: int = 10) -> dict:
        await self._ensure_token()
        r = await self._get("/api/v1/items", headers=self._h,
                            params={"q": query, "pageSize": str(limit)})
        items = r.get("items", []) if isinstance(r, dict) else []
        return {
            "count": r.get("total", len(items)) if isinstance(r, dict) else 0,
            "items": [{"id": i.get("id"), "name": i.get("name"),
                       "location": (i.get("location") or {}).get("name")} for i in items],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="homebox_search",
                description="Search Homebox inventory for items by name or description.",
                handler=self.search,
                params={
                    "query": {"type": "string", "required": True},
                    "limit": {"type": "integer", "default": 10},
                },
            ),
        ]
