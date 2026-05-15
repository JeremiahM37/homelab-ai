"""Service plugin system.

A service is anything in your homelab with an HTTP API. The plugin tells
homelab-ai how to:
  - check its health (for the monitoring agent),
  - restart / repair it (for the fixer),
  - expose actions as tools (for the AI agent / MCP server).

Built-in plugins live in this package. User plugins live in
`~/.config/homelab-ai/services/` and are loaded by file basename.
"""
from .base import Service, ToolSpec
from .registry import load_services

__all__ = ["Service", "ToolSpec", "load_services"]
