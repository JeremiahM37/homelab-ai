"""Paperless-ngx plugin — document management + OCR."""
from __future__ import annotations

from .base import Service, ToolSpec


class Paperless(Service):
    name = "paperless"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if token := self.config.get("token") or self.config.get("api_key"):
            h["Authorization"] = f"Token {token}"
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/", headers=self._headers)
            return {"ok": True, "endpoints": len(r) if isinstance(r, dict) else 0}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def search(self, query: str, limit: int = 10) -> dict:
        r = await self._get(
            "/api/documents/",
            headers=self._headers,
            params={"query": query, "page_size": str(limit)},
        )
        items = r.get("results", []) if isinstance(r, dict) else []
        return {
            "count": r.get("count", len(items)) if isinstance(r, dict) else 0,
            "items": [
                {
                    "id": d.get("id"),
                    "title": d.get("title"),
                    "created": d.get("created"),
                    "tags": d.get("tags"),
                }
                for d in items
            ],
        }

    async def tag(self, document_id: int, tag_name: str) -> dict:
        # Look up the tag id.
        tags = await self._get("/api/tags/", headers=self._headers)
        tag_id = next((t["id"] for t in tags.get("results", []) if t["name"] == tag_name), None)
        if tag_id is None:
            return {"error": f"tag {tag_name!r} not found"}
        doc = await self._get(f"/api/documents/{document_id}/", headers=self._headers)
        existing = set(doc.get("tags", []))
        existing.add(tag_id)
        await self._patch(f"/api/documents/{document_id}/", headers=self._headers,
                          json={"tags": list(existing)})
        return {"ok": True, "tag": tag_name, "document_id": document_id}

    async def _patch(self, path: str, **kwargs) -> dict:
        url = self.config["url"].rstrip("/") + path
        async with self.http.patch(url, **kwargs) as r:
            r.raise_for_status()
            return await r.json() if r.content_length else {}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="paperless_search",
                description="Search the Paperless-ngx document library by query (full-text).",
                handler=self.search,
                params={
                    "query": {"type": "string", "description": "Search text", "required": True},
                    "limit": {"type": "integer", "default": 10},
                },
            ),
            ToolSpec(
                name="paperless_tag",
                description="Add a tag to a specific Paperless document.",
                handler=self.tag,
                params={
                    "document_id": {"type": "integer", "description": "Document ID", "required": True},
                    "tag_name": {"type": "string", "description": "Tag name", "required": True},
                },
            ),
        ]
