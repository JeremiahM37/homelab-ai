"""Smoke: every public module imports cleanly."""
import importlib


MODULES = [
    "homelab_ai",
    "homelab_ai.config",
    "homelab_ai.agent.loop",
    "homelab_ai.agent.failure_memory",
    "homelab_ai.agent.modules.base",
    "homelab_ai.agent.modules.service_health",
    "homelab_ai.agent.modules.disk_watcher",
    "homelab_ai.agent.modules.container_doctor",
    "homelab_ai.fixer.audit",
    "homelab_ai.fixer.backup",
    "homelab_ai.fixer.tier1_rules",
    "homelab_ai.services.base",
    "homelab_ai.services.registry",
    "homelab_ai.services.arr",
    "homelab_ai.services.sonarr",
    "homelab_ai.services.radarr",
    "homelab_ai.services.jellyfin",
    "homelab_ai.services.qbittorrent",
    "homelab_ai.services.ollama",
    "homelab_ai.mcp.tool_router",
    "homelab_ai.mcp.server",
    "homelab_ai.verify.runner",
    "homelab_ai.verify.builtin_checks",
    "homelab_ai.api.main",
    "homelab_ai.api.routers.agent",
    "homelab_ai.api.routers.ai",
    "homelab_ai.api.routers.services",
    "homelab_ai.api.routers.settings",
]


def test_every_module_imports():
    for m in MODULES:
        importlib.import_module(m)
