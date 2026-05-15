"""n8n plugin — workflow automation."""
from __future__ import annotations

from .base import Service, ToolSpec


class N8N(Service):
    name = "n8n"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if key := self.config.get("api_key"):
            h["X-N8N-API-KEY"] = key
        return h

    async def health(self) -> dict:
        try:
            await self._get("/api/v1/workflows", headers=self._headers,
                            params={"limit": "1"})
            return {"ok": True, "reachable": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_workflows(self, active_only: bool = True) -> dict:
        params = {"limit": "100"}
        if active_only:
            params["active"] = "true"
        r = await self._get("/api/v1/workflows", headers=self._headers, params=params)
        items = r.get("data", []) if isinstance(r, dict) else []
        return {
            "count": len(items),
            "workflows": [
                {"id": w.get("id"), "name": w.get("name"),
                 "active": w.get("active"), "updated_at": w.get("updatedAt")}
                for w in items[:50]
            ],
        }

    async def recent_executions(self, limit: int = 20) -> dict:
        r = await self._get("/api/v1/executions", headers=self._headers,
                            params={"limit": str(limit)})
        items = r.get("data", []) if isinstance(r, dict) else []
        return {
            "count": len(items),
            "executions": [
                {
                    "id": e.get("id"),
                    "workflow_id": e.get("workflowId"),
                    "status": e.get("status"),
                    "finished": e.get("finished"),
                    "stopped_at": e.get("stoppedAt"),
                }
                for e in items[:limit]
            ],
        }

    async def failed_executions(self) -> dict:
        r = await self.recent_executions(limit=100)
        failed = [e for e in r.get("executions", [])
                  if e.get("status") in ("error", "failed", "crashed")]
        return {"count": len(failed), "failed": failed[:20]}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="n8n_list_workflows",
                description="List configured n8n workflows.",
                handler=self.list_workflows,
                params={"active_only": {"type": "boolean", "default": True}},
            ),
            ToolSpec(
                name="n8n_recent_executions",
                description="Recent n8n workflow executions (last N).",
                handler=self.recent_executions,
                params={"limit": {"type": "integer", "default": 20}},
            ),
            ToolSpec(
                name="n8n_failed_executions",
                description="Recent n8n workflow executions that failed or errored.",
                handler=self.failed_executions,
            ),
        ]
