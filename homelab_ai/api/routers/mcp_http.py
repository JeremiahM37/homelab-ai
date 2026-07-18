"""HTTP MCP server endpoint — opt-in alongside the stdio server.

For clients that prefer an HTTP MCP transport over launching a subprocess.
Implements the minimum: tools/list + tools/call over JSON-RPC 2.0 POST.

Off by default — only registered when `features.mcp_http.enabled` is true.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

logger = logging.getLogger("homelab_ai.api.mcp_http")
router = APIRouter(tags=["mcp"])


def _gather_tools(services: dict) -> tuple[list[dict], dict]:
    """Collect every service tool as MCP tool descriptors plus a handler map."""
    tools = []
    handlers: dict[str, Any] = {}
    for svc_name, svc in services.items():
        for spec in svc.tools():
            tools.append({
                "name": spec.name,
                "description": f"[{svc_name}] {spec.description}",
                "inputSchema": spec.json_schema(),
            })
            handlers[spec.name] = spec.handler
    return tools, handlers


@router.post("/mcp")
async def mcp_rpc(request: Request, body: dict = Body(...)) -> dict:
    """JSON-RPC 2.0 endpoint. Supports `tools/list` + `tools/call`."""
    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params") or {}

    services = request.app.state.services
    tools, handlers = _gather_tools(services)

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "homelab-ai", "version": "0.4.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = handlers.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"unknown tool: {name}"}}
        try:
            result = await handler(**arguments)
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text",
                                    "text": json.dumps(result, default=str, indent=2)}]},
        }

    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"unknown method: {method}"}}
