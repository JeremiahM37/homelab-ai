"""SearXNG plugin — self-hosted metasearch. Doubles as the web-search tool
for the AI agent so it can answer non-homelab questions.
"""
from __future__ import annotations

from .base import Service, ToolSpec


class SearXNG(Service):
    name = "searxng"

    async def health(self) -> dict:
        try:
            r = await self._get("/healthz")
            return {"ok": True, "detail": str(r)[:80]}
        except Exception as e:
            try:
                # Some installs lack /healthz; fall back to root.
                r = await self._get("/", params={"format": "json", "q": "test"})
                return {"ok": True}
            except Exception:
                return {"ok": False, "error": str(e)[:200]}

    async def web_search(self, query: str, limit: int = 5) -> dict:
        url = self.config["url"].rstrip("/") + "/search"
        async with self.http.get(url, params={"q": query, "format": "json"}) as r:
            r.raise_for_status()
            data = await r.json()
        results = (data.get("results") or [])[:limit]
        return {
            "count": len(results),
            "results": [
                {"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:300]}
                for r in results
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="web_search",
                description="Search the public web via SearXNG. Use for current events, how-to, or anything not about the user's homelab itself.",
                handler=self.web_search,
                params={
                    "query": {"type": "string", "required": True},
                    "limit": {"type": "integer", "default": 5},
                },
            ),
        ]
