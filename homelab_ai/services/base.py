"""Base class every service plugin inherits from."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import aiohttp

logger = logging.getLogger("homelab_ai.services")


@dataclass
class ToolSpec:
    """Description of a callable the AI agent / MCP server can invoke.

    `params` is a dict of param_name -> {type, description, default?, required?}.
    The router builds a JSON schema from it for tool-calling LLMs.

    Example:
        params={
            "query": {"type": "string", "description": "Search text", "required": True},
            "limit": {"type": "integer", "description": "Max results", "default": 10},
        }
    """
    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    params: dict[str, dict] = field(default_factory=dict)

    def json_schema(self) -> dict:
        """Build an OpenAI-style function-calling schema for this tool."""
        properties = {}
        required = []
        for pname, pdef in self.params.items():
            ptype = pdef.get("type", "string")
            entry = {"type": ptype, "description": pdef.get("description", "")}
            if "default" in pdef:
                entry["default"] = pdef["default"]
            properties[pname] = entry
            if pdef.get("required", "default" not in pdef):
                required.append(pname)
        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema


class Service:
    """Override in subclasses.

    Subclasses should set `name` (matching the config.yaml key) and override
    `health()`. Override `restart()` if there's a way to recover the service
    without operator action. Override `tools()` to expose AI-callable
    functions.
    """
    name: str = "base"

    def __init__(self, config: dict, http: aiohttp.ClientSession):
        self.config = config
        self.http = http

    # ── lifecycle ────────────────────────────────────────────────────────
    async def health(self) -> dict:
        """Return a small dict with at least {"ok": bool}. Used by the agent."""
        return {"ok": True}

    async def restart(self) -> dict:
        """Optional. Return {"ok": bool, "detail": str}. Default: not supported."""
        return {"ok": False, "detail": "no restart handler for this service"}

    # ── AI surface ───────────────────────────────────────────────────────
    def tools(self) -> list[ToolSpec]:
        """Return tool specs the AI agent and MCP server should expose."""
        return []

    # ── helpers ──────────────────────────────────────────────────────────
    async def _get(self, path: str, **kwargs) -> dict:
        url = self.config["url"].rstrip("/") + path
        async with self.http.get(url, **kwargs) as r:
            r.raise_for_status()
            return await r.json()

    async def _post(self, path: str, **kwargs) -> dict:
        url = self.config["url"].rstrip("/") + path
        async with self.http.post(url, **kwargs) as r:
            r.raise_for_status()
            return await r.json() if r.content_length else {}

    @property
    def _api_headers(self) -> dict:
        h = {}
        if key := self.config.get("api_key"):
            h["X-Api-Key"] = key
        return h
