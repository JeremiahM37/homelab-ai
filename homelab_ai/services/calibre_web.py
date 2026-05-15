"""Calibre-Web plugin — ebook library (OPDS browsing + search).

Calibre-Web's main programmatic surface is its OPDS feed. We query the
OPDS search endpoint and parse the Atom XML inline (xml.etree).
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import aiohttp

from .base import Service, ToolSpec


class CalibreWeb(Service):
    name = "calibre_web"

    @property
    def _auth(self) -> aiohttp.BasicAuth | None:
        u, p = self.config.get("username"), self.config.get("password")
        if u and p:
            return aiohttp.BasicAuth(u, p)
        return None

    async def health(self) -> dict:
        try:
            url = self.config["url"].rstrip("/") + "/opds"
            async with self.http.get(url, auth=self._auth,
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                return {"ok": r.status < 400, "status": r.status}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def search(self, query: str, limit: int = 10) -> dict:
        url = self.config["url"].rstrip("/") + "/opds/search/" + query
        async with self.http.get(url, auth=self._auth,
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
            r.raise_for_status()
            xml = await r.text()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml)
        entries = root.findall("a:entry", ns)[:limit]
        out = []
        for e in entries:
            title = (e.find("a:title", ns).text if e.find("a:title", ns) is not None else "")
            author = ""
            a_el = e.find("a:author", ns)
            if a_el is not None:
                n = a_el.find("a:name", ns)
                if n is not None:
                    author = n.text or ""
            out.append({"title": title, "author": author})
        return {"count": len(out), "results": out}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="calibre_web_search",
                description="Search the Calibre-Web ebook library via OPDS.",
                handler=self.search,
                params={
                    "query": {"type": "string", "required": True},
                    "limit": {"type": "integer", "default": 10},
                },
            ),
        ]
