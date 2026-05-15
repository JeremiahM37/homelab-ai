"""changedetection.io plugin — website change monitor.

API: /api/v1/watch (list) and /api/v1/watch/<uuid> (detail). Auth via
`x-api-key` header.
"""
from __future__ import annotations

from .base import Service, ToolSpec


class ChangeDetection(Service):
    name = "changedetection"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if key := self.config.get("api_key"):
            h["x-api-key"] = key
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/v1/watch", headers=self._headers)
            return {"ok": True, "watch_count": len(r) if isinstance(r, dict) else 0}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_watches(self) -> dict:
        r = await self._get("/api/v1/watch", headers=self._headers)
        if not isinstance(r, dict):
            return {"watches": []}
        return {
            "count": len(r),
            "watches": [
                {
                    "uuid": uuid,
                    "title": w.get("title") or w.get("url"),
                    "url": w.get("url"),
                    "last_changed": w.get("last_changed"),
                    "last_checked": w.get("last_checked"),
                    "viewed": w.get("viewed"),
                }
                for uuid, w in list(r.items())[:50]
            ],
        }

    async def changed_recently(self) -> dict:
        r = await self._get("/api/v1/watch", headers=self._headers)
        if not isinstance(r, dict):
            return {"changed": []}
        # `viewed: False` means the user hasn't acknowledged the latest change.
        changed = [
            {"uuid": uuid, "title": w.get("title") or w.get("url"),
             "url": w.get("url"), "last_changed": w.get("last_changed")}
            for uuid, w in r.items()
            if not w.get("viewed") and w.get("last_changed")
        ]
        return {"count": len(changed), "changed": changed}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="changedetection_list_watches",
                description="List all configured website-change watches.",
                handler=self.list_watches,
            ),
            ToolSpec(
                name="changedetection_changed_recently",
                description="Sites that changed since the user last viewed them.",
                handler=self.changed_recently,
            ),
        ]
