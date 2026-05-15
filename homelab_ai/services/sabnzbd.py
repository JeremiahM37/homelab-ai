"""SABnzbd plugin — Usenet downloader."""
from __future__ import annotations

from .base import Service, ToolSpec


class Sabnzbd(Service):
    name = "sabnzbd"

    def _api_params(self, extra: dict | None = None) -> dict:
        p = {"mode": "queue", "output": "json"}
        if key := self.config.get("api_key"):
            p["apikey"] = key
        if extra:
            p.update(extra)
        return p

    async def health(self) -> dict:
        try:
            r = await self._get("/api", params={**self._api_params(), "mode": "version"})
            return {"ok": True, "version": r.get("version")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def queue(self) -> dict:
        r = await self._get("/api", params=self._api_params())
        q = r.get("queue", {}) if isinstance(r, dict) else {}
        return {
            "speed": q.get("speed"),
            "size_left": q.get("sizeleft"),
            "slot_count": len(q.get("slots", [])),
            "paused": q.get("paused"),
            "slots": [
                {"filename": s.get("filename"), "percentage": s.get("percentage"), "status": s.get("status")}
                for s in (q.get("slots") or [])[:10]
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="sabnzbd_queue",
                description="Get SABnzbd download queue (speed, size left, items).",
                handler=self.queue,
            ),
        ]
