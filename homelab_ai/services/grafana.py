"""Grafana plugin — dashboards + alerting.

Auth: Bearer token (service account or API key).
"""
from __future__ import annotations

import logging

from .base import Service, ToolSpec

logger = logging.getLogger("homelab_ai.services.grafana")


class Grafana(Service):
    name = "grafana"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if key := self.config.get("api_key") or self.config.get("token"):
            h["Authorization"] = f"Bearer {key}"
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/health", headers=self._headers)
            return {"ok": r.get("database") == "ok", "version": r.get("version")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_dashboards(self, query: str = "") -> dict:
        params = {"type": "dash-db", "limit": "30"}
        if query:
            params["query"] = query
        r = await self._get("/api/search", headers=self._headers, params=params)
        items = r if isinstance(r, list) else []
        return {
            "count": len(items),
            "dashboards": [
                {"uid": d.get("uid"), "title": d.get("title"),
                 "tags": d.get("tags"), "url": d.get("url")}
                for d in items
            ],
        }

    async def firing_alerts(self) -> dict:
        # Grafana 9+ Alertmanager-style alerts API. Older versions used
        # /api/alerts — we return a stitched result so both work.
        for path in ("/api/alertmanager/grafana/api/v2/alerts",
                     "/api/alerts"):
            try:
                r = await self._get(path, headers=self._headers)
            except Exception as e:
                logger.debug("alerts endpoint %s unavailable: %s", path, e)
                continue
            if isinstance(r, list):
                # Old shape: list of alert dicts with state.
                firing = [a for a in r if a.get("state") in ("alerting", "firing")]
                return {
                    "count": len(firing),
                    "alerts": [{"name": a.get("name"), "state": a.get("state"),
                                "dashboard_id": a.get("dashboardId")} for a in firing[:50]],
                }
            if isinstance(r, dict):
                # AM shape: top-level dict containing alerts list (rare path).
                alerts = r.get("alerts") or []
                return {"count": len(alerts), "alerts": alerts[:50]}
        return {"count": 0, "alerts": []}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="grafana_list_dashboards",
                description="List Grafana dashboards, optionally filtered by query.",
                handler=self.list_dashboards,
                params={"query": {"type": "string", "default": ""}},
            ),
            ToolSpec(
                name="grafana_firing_alerts",
                description="Get currently-firing Grafana alerts.",
                handler=self.firing_alerts,
            ),
        ]
