"""MCP stdio server — exposes every loaded tool to MCP clients.

Used by Claude Desktop, Cursor, and any other MCP-aware host that runs an
MCP server as a subprocess and speaks JSON-RPC over stdio.

Wire it up in Claude Desktop's `mcpServers` config:

    {
      "mcpServers": {
        "homelab-ai": {
          "command": "homelab-ai",
          "args": ["--config", "/path/to/config.yaml", "mcp-server"]
        }
      }
    }

Implementation: uses the official `mcp` Python package. If it's not
installed, the subcommand prints a helpful message instead of crashing.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING

import aiohttp

from homelab_ai.services import load_services

if TYPE_CHECKING:
    from homelab_ai.config import Config

logger = logging.getLogger("homelab_ai.mcp")


def _require_mcp():
    try:
        import mcp  # noqa: F401
        import mcp.server  # noqa: F401
        import mcp.server.stdio  # noqa: F401
        import mcp.types  # noqa: F401
    except ImportError:
        print(
            "ERROR: the `mcp` package is not installed.\n"
            "Install it with:  pip install homelab-ai[mcp]\n"
            "or:               pip install mcp",
            file=sys.stderr,
        )
        sys.exit(2)


async def _run(cfg: "Config") -> None:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        services = load_services(cfg, http)
        # Flatten tools.
        all_tools = []
        handlers = {}
        for svc_name, svc in services.items():
            for spec in svc.tools():
                all_tools.append(Tool(
                    name=spec.name,
                    description=f"[{svc_name}] {spec.description}",
                    inputSchema=spec.json_schema(),
                ))
                handlers[spec.name] = spec.handler

        server = Server("homelab-ai")

        @server.list_tools()
        async def _list():
            return all_tools

        @server.call_tool()
        async def _call(name: str, arguments: dict | None):
            handler = handlers.get(name)
            if not handler:
                return [TextContent(type="text", text=f"unknown tool: {name}")]
            try:
                result = await handler(**(arguments or {}))
            except Exception as e:
                return [TextContent(type="text", text=f"tool error: {type(e).__name__}: {e}")]
            import json
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def run_mcp_server(cfg: "Config") -> int:
    """Entry point from the CLI."""
    _require_mcp()
    try:
        asyncio.run(_run(cfg))
    except KeyboardInterrupt:
        pass
    return 0
