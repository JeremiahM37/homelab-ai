"""Built-in verification checks. Examples and starting points."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp

from .runner import check

if TYPE_CHECKING:
    from homelab_ai.config import Config


@check(group="core")
def config_loads(cfg: Config) -> None:
    """Smoke: the config dataclass exists and has sane defaults."""
    assert cfg.agent.scan_interval >= 30, "scan_interval too short"
    assert cfg.server.port > 0


@check(group="core")
def fixer_caps_present(cfg: Config) -> None:
    """Tier-3 caps must be set or the smart fixer is unsafe."""
    f = cfg.agent.fixer
    assert f.max_files_changed_per_fix >= 1
    assert f.max_lines_changed_per_fix >= 10
    assert f.audit_log, "audit_log path must be set"
    assert f.backup_dir, "backup_dir must be set"


@check(group="services")
def services_reachable(cfg: Config) -> str | None:
    """Hit /api/overview through the loaded service plugins."""
    if not cfg.services:
        return "no services configured — nothing to check"

    async def _run():
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            from homelab_ai.services import load_services
            svcs = load_services(cfg, http)
            failed = []
            for name, svc in svcs.items():
                try:
                    r = await svc.health()
                    if not r.get("ok"):
                        failed.append((name, r.get("error", "ok=false")))
                except Exception as e:
                    failed.append((name, str(e)[:200]))
            return failed

    failed = asyncio.run(_run())
    if failed:
        msg = "; ".join(f"{n}: {e}" for n, e in failed)
        # A service being unhealthy is a warning here, not a hard failure —
        # otherwise verify would always go red whenever you have a known-broken
        # service. The agent's auto-repair loop owns hard failures.
        return f"unhealthy services: {msg}"
    return None


@check(group="ai")
def ollama_reachable(cfg: Config) -> str | None:
    """Confirm the configured Ollama URL responds. Warning, not hard fail."""
    async def _run():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as http:
                async with http.get(f"{cfg.ollama.url}/api/tags") as r:
                    return r.status
        except Exception as e:
            return str(e)
    out = asyncio.run(_run())
    if out != 200:
        return f"ollama not reachable at {cfg.ollama.url}: {out}"
    return None
