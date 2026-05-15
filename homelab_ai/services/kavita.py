"""Kavita plugin — comic / manga / ebook reader."""
from __future__ import annotations

from .base import Service, ToolSpec


class Kavita(Service):
    name = "kavita"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if key := self.config.get("api_key"):
            h["Authorization"] = f"Bearer {key}"
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/Server/server-info-slim", headers=self._headers)
            return {"ok": True, "kavita_version": r.get("kavitaVersion")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def libraries(self) -> dict:
        r = await self._get("/api/Library/libraries", headers=self._headers)
        libs = r if isinstance(r, list) else []
        return {"count": len(libs), "libraries": [{"id": lib.get("id"), "name": lib.get("name")} for lib in libs]}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="kavita_libraries",
                description="List Kavita libraries (comics, manga, books).",
                handler=self.libraries,
            ),
        ]
