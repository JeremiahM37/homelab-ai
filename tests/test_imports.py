"""Smoke: every public module imports cleanly. Catches typos + circulars."""
import importlib

MODULES = [
    # core
    "homelab_ai",
    "homelab_ai.config",
    # agent
    "homelab_ai.agent.loop",
    "homelab_ai.agent.failure_memory",
    "homelab_ai.agent.modules.base",
    "homelab_ai.agent.modules.service_health",
    "homelab_ai.agent.modules.disk_watcher",
    "homelab_ai.agent.modules.disk_forecast",
    "homelab_ai.agent.modules.container_doctor",
    "homelab_ai.agent.modules.container_resources",
    "homelab_ai.agent.modules.vpn_watchdog",
    "homelab_ai.agent.modules.import_watchdog",
    # fixer
    "homelab_ai.fixer.audit",
    "homelab_ai.fixer.backup",
    "homelab_ai.fixer.tier1_rules",
    "homelab_ai.fixer.tier2_small",
    "homelab_ai.fixer.tier3_smart",
    # services (builtin)
    "homelab_ai.services.base",
    "homelab_ai.services.registry",
    "homelab_ai.services.arr",
    "homelab_ai.services.sonarr",
    "homelab_ai.services.radarr",
    "homelab_ai.services.lidarr",
    "homelab_ai.services.readarr",
    "homelab_ai.services.prowlarr",
    "homelab_ai.services.bazarr",
    "homelab_ai.services.jellyfin",
    "homelab_ai.services.qbittorrent",
    "homelab_ai.services.transmission",
    "homelab_ai.services.sabnzbd",
    "homelab_ai.services.ollama",
    "homelab_ai.services.paperless",
    "homelab_ai.services.immich",
    "homelab_ai.services.audiobookshelf",
    "homelab_ai.services.kavita",
    "homelab_ai.services.mealie",
    "homelab_ai.services.homebox",
    "homelab_ai.services.uptime_kuma",
    "homelab_ai.services.home_assistant",
    "homelab_ai.services.adguard",
    "homelab_ai.services.searxng",
    "homelab_ai.services.nextcloud",
    "homelab_ai.services.jellyseerr",
    "homelab_ai.services.overseerr",
    "homelab_ai.services.command",
    # mcp + llm
    "homelab_ai.llm",
    "homelab_ai.llm.base",
    "homelab_ai.llm.ollama",
    "homelab_ai.llm.openai_compat",
    "homelab_ai.mcp.tool_router",
    "homelab_ai.mcp.server",
    # auth + discovery + wizard
    "homelab_ai.auth",
    "homelab_ai.auth.passwords",
    "homelab_ai.auth.sessions",
    "homelab_ai.auth.middleware",
    "homelab_ai.discovery",
    "homelab_ai.discovery.probe",
    "homelab_ai.init_wizard",
    # api
    "homelab_ai.api.main",
    "homelab_ai.api.routers.agent",
    "homelab_ai.api.routers.ai",
    "homelab_ai.api.routers.auth",
    "homelab_ai.api.routers.services",
    "homelab_ai.api.routers.settings",
    # notifications + verify
    "homelab_ai.notifications.notifier",
    "homelab_ai.verify.runner",
    "homelab_ai.verify.builtin_checks",
]


def test_every_module_imports():
    for m in MODULES:
        importlib.import_module(m)
