"""MCP server — exposes the tool catalog to MCP-compatible clients (Claude
Desktop, Open WebUI, Cursor, etc.).

The MCP protocol layer is intentionally thin: every tool the AI agent has,
the MCP server also exposes. This means user-added plugins automatically
work in Claude Desktop without extra wiring.
"""
from .tool_router import SemanticToolRouter

__all__ = ["SemanticToolRouter"]
