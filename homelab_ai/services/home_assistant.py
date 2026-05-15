"""Home Assistant plugin — IoT / smart home."""
from __future__ import annotations

from .base import Service, ToolSpec


class HomeAssistant(Service):
    name = "home_assistant"

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if token := self.config.get("token") or self.config.get("api_key"):
            h["Authorization"] = f"Bearer {token}"
        return h

    async def health(self) -> dict:
        try:
            r = await self._get("/api/", headers=self._headers)
            return {"ok": True, "message": r.get("message", "running")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def get_state(self, entity_id: str) -> dict:
        return await self._get(f"/api/states/{entity_id}", headers=self._headers)

    async def list_states(self, domain: str | None = None) -> dict:
        r = await self._get("/api/states", headers=self._headers)
        if not isinstance(r, list):
            return {"count": 0, "entities": []}
        if domain:
            r = [e for e in r if e.get("entity_id", "").startswith(f"{domain}.")]
        return {
            "count": len(r),
            "entities": [
                {"id": e.get("entity_id"), "state": e.get("state")}
                for e in r[:50]
            ],
        }

    async def call_service(self, domain: str, service: str, entity_id: str) -> dict:
        path = f"/api/services/{domain}/{service}"
        body = {"entity_id": entity_id}
        await self._post(path, headers=self._headers, json=body)
        return {"ok": True, "called": f"{domain}.{service}", "entity_id": entity_id}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="ha_get_state",
                description="Get the current state of a Home Assistant entity (e.g. 'light.kitchen').",
                handler=self.get_state,
                params={"entity_id": {"type": "string", "required": True}},
            ),
            ToolSpec(
                name="ha_list_states",
                description="List Home Assistant entities, optionally filtered by domain (e.g. 'light').",
                handler=self.list_states,
                params={"domain": {"type": "string", "default": ""}},
            ),
            ToolSpec(
                name="ha_call_service",
                description="Call a Home Assistant service against an entity (e.g. domain='light', service='turn_on', entity_id='light.kitchen').",
                handler=self.call_service,
                params={
                    "domain": {"type": "string", "required": True},
                    "service": {"type": "string", "required": True},
                    "entity_id": {"type": "string", "required": True},
                },
            ),
        ]
