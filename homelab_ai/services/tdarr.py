"""Tdarr plugin — automated transcoding farm."""
from __future__ import annotations

from .base import Service, ToolSpec


class Tdarr(Service):
    name = "tdarr"

    async def _stats(self) -> dict:
        # Tdarr exposes its UI data through /api/v2/cruddb with a `data` body.
        # The server-stats collection is a single doc with all the counters.
        try:
            r = await self._post(
                "/api/v2/cruddb",
                json={
                    "data": {
                        "collection": "StatisticsJSONDB",
                        "mode": "getById",
                        "docID": "statistics",
                    },
                },
            )
        except Exception as e:
            return {"error": str(e)[:200]}
        return r if isinstance(r, dict) else {}

    async def health(self) -> dict:
        try:
            await self._stats()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def server_stats(self) -> dict:
        s = await self._stats()
        return {
            "library_files": s.get("totalFileCount") or s.get("table1Count"),
            "transcode_queue": s.get("table3Count"),    # files queued
            "health_check_queue": s.get("table6Count"),
            "transcoded_total": s.get("table4Count"),
            "errors": s.get("table2Count"),
        }

    async def queue_depth(self) -> dict:
        s = await self._stats()
        return {
            "transcode_queue": s.get("table3Count", 0),
            "errored": s.get("table2Count", 0),
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="tdarr_server_stats",
                description="Get Tdarr summary: library size, transcoded, queued, errored.",
                handler=self.server_stats,
            ),
            ToolSpec(
                name="tdarr_queue_depth",
                description="How many files are currently queued for Tdarr transcoding.",
                handler=self.queue_depth,
            ),
        ]
