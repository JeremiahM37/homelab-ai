"""Generic *arr-app base. Subclassed by sonarr / radarr / readarr / lidarr.

All *arr apps share the same `/api/v3/system/status`, `/api/v3/health`,
`/api/v3/queue` shape so most of the plugin is shared. Subclasses add
service-specific tools (e.g. Sonarr exposes upcoming-episodes, Radarr
exposes missing-movies).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .base import Service, ToolSpec


class ArrBase(Service):
    """Base for Sonarr-family services. Set `name` and `api_path` in subclass."""
    name = "arr"
    api_path = "/api/v3"

    async def health(self) -> dict:
        try:
            status = await self._get(f"{self.api_path}/system/status", headers=self._api_headers)
            issues = await self._get(f"{self.api_path}/health", headers=self._api_headers)
            return {
                "ok": True,
                "version": status.get("version"),
                "health_issues": len(issues),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def queue_summary(self) -> dict:
        q = await self._get(f"{self.api_path}/queue", headers=self._api_headers)
        records = q.get("records") if isinstance(q, dict) else []
        return {
            "total": q.get("totalRecords", len(records)) if isinstance(q, dict) else 0,
            "downloading": sum(1 for r in records if r.get("status") == "downloading"),
            "warning": sum(1 for r in records if r.get("trackedDownloadStatus") == "warning"),
        }

    async def calendar(self, days: int = 7) -> dict:
        """Upcoming items in the next N days. Works for sonarr + radarr."""
        start = datetime.now(UTC).isoformat()
        end = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        items = await self._get(
            f"{self.api_path}/calendar",
            headers=self._api_headers,
            params={"start": start, "end": end},
        )
        items = items if isinstance(items, list) else []
        return {
            "count": len(items),
            "upcoming": [
                {
                    "title": i.get("series", {}).get("title") or i.get("title"),
                    "name": i.get("title"),  # episode title for sonarr
                    "air_date": i.get("airDateUtc") or i.get("digitalRelease") or i.get("inCinemas"),
                }
                for i in items[:50]
            ],
        }

    async def history(self, limit: int = 20) -> dict:
        r = await self._get(
            f"{self.api_path}/history",
            headers=self._api_headers,
            params={"pageSize": str(limit)},
        )
        records = r.get("records", []) if isinstance(r, dict) else []
        return {
            "count": r.get("totalRecords", len(records)) if isinstance(r, dict) else 0,
            "events": [
                {
                    "event": rec.get("eventType"),
                    "date": rec.get("date"),
                    "name": rec.get("sourceTitle") or (rec.get("movie") or {}).get("title") or (rec.get("series") or {}).get("title"),
                }
                for rec in records[:limit]
            ],
        }

    async def missing(self, limit: int = 20) -> dict:
        path = f"{self.api_path}/wanted/missing"
        r = await self._get(
            path, headers=self._api_headers,
            params={"pageSize": str(limit), "sortKey": "airDateUtc", "sortDirection": "descending"},
        )
        records = r.get("records", []) if isinstance(r, dict) else []
        return {
            "count": r.get("totalRecords", len(records)) if isinstance(r, dict) else 0,
            "missing": [
                {
                    "name": rec.get("title"),
                    "series": (rec.get("series") or {}).get("title"),
                    "air_date": rec.get("airDateUtc"),
                }
                for rec in records[:limit]
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=f"{self.name}_queue_summary",
                description=f"Summarize the {self.name} download queue.",
                handler=self.queue_summary,
            ),
            ToolSpec(
                name=f"{self.name}_health",
                description=f"Check {self.name} health and version.",
                handler=self.health,
            ),
            ToolSpec(
                name=f"{self.name}_calendar",
                description=f"List upcoming {self.name} items in the next N days.",
                handler=self.calendar,
                params={"days": {"type": "integer", "description": "Lookahead days", "default": 7}},
            ),
            ToolSpec(
                name=f"{self.name}_history",
                description=f"Recent {self.name} history (grabbed, imported, failed events).",
                handler=self.history,
                params={"limit": {"type": "integer", "default": 20}},
            ),
            ToolSpec(
                name=f"{self.name}_missing",
                description=f"List missing {self.name} items (wanted but not yet downloaded).",
                handler=self.missing,
                params={"limit": {"type": "integer", "default": 20}},
            ),
        ]


class Sonarr(ArrBase):
    name = "sonarr"


class Radarr(ArrBase):
    name = "radarr"


class Lidarr(ArrBase):
    name = "lidarr"


class Readarr(ArrBase):
    name = "readarr"


class Prowlarr(ArrBase):
    name = "prowlarr"
    api_path = "/api/v1"


class Bazarr(ArrBase):
    name = "bazarr"
    api_path = "/api"
