"""Agent scan loop.

`run_forever(cfg)` is the long-lived entrypoint. `scan_once(cfg)` runs a
single scan and returns — useful for cron / CLI / tests.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

from .failure_memory import FailureMemory
from .modules import AgentModule, Finding, Severity

if TYPE_CHECKING:
    from homelab_ai.config import Config
    from homelab_ai.services.base import Service

logger = logging.getLogger("homelab_ai.agent")


def _user_agent_module_dirs() -> list[Path]:
    import os
    dirs = [Path.home() / ".config" / "homelab-ai" / "agent_modules"]
    if extra := os.environ.get("HOMELAB_AI_AGENT_MODULES"):
        dirs.append(Path(extra))
    return [d for d in dirs if d.is_dir()]


def _load_modules(cfg: Config, services: dict[str, Service]) -> list[AgentModule]:
    import importlib.util as _ilu

    out: list[AgentModule] = []
    for name in cfg.agent.modules:
        module = None
        try:
            module = importlib.import_module(f"homelab_ai.agent.modules.{name}")
        except ImportError:
            for d in _user_agent_module_dirs():
                path = d / f"{name}.py"
                if path.is_file():
                    try:
                        spec = _ilu.spec_from_file_location(f"user_modules.{name}", path)
                        module = _ilu.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        break
                    except Exception as e:
                        logger.warning("failed to load user agent module %s: %s", path, e)
            if module is None:
                logger.warning("agent module %r not found", name)
                continue

        # Prefer a class whose `.name` matches what was requested. This lets
        # one file define multiple AgentModule subclasses without accidentally
        # instantiating the wrong one — important if a user organizes their
        # checks per-file as ([Backups, Disks, Networks] all in `monitor.py`).
        candidates: list[type[AgentModule]] = []
        for _n, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, AgentModule) and obj is not AgentModule:
                candidates.append(obj)
        cls = None
        for c in candidates:
            if getattr(c, "name", None) == name:
                cls = c
                break
        if cls is None:
            # Fall back: a class defined in this module (not a re-import) wins.
            for c in candidates:
                if c.__module__ == module.__name__:
                    cls = c
                    break
            if cls is None and candidates:
                cls = candidates[0]
        if not cls:
            logger.warning("no AgentModule subclass in %s", module.__name__)
            continue
        out.append(cls(cfg, services))
    return out


async def _do_scan(
    modules: list[AgentModule],
    memory: FailureMemory,
    services: dict[str, Service],
    http: aiohttp.ClientSession,
    cfg: Config,
) -> dict:
    from homelab_ai.fixer import tier1_rules, tier2_small
    from homelab_ai.fixer.tier3_smart import SmartFixer
    from homelab_ai.notifications import Notifier

    started = time.time()
    notifier = Notifier(cfg.agent.notify, http, state_path=Path("./data/notifier.json"))
    findings: list[Finding] = []
    for m in modules:
        try:
            findings.extend(await m.scan())
        except Exception as e:
            logger.exception("module %s raised: %s", m.name, e)

    # Resolve previously-open failures that didn't come back this scan.
    current_fps = {f"{f.module}|{f.target}|{f.message[:200]}" for f in findings}
    for prev in memory.open_failures():
        prev_fp = f"{prev['module']}|{prev['target']}|{prev['error'][:200]}"
        if prev_fp in current_fps:
            continue
        memory.mark_resolved(prev["fingerprint"])
        # Build a stub Finding for the notifier (we don't have the original object).
        from homelab_ai.agent.modules.base import Finding as _F
        from homelab_ai.agent.modules.base import Severity as _Sev
        await notifier.publish_resolved(_F(
            module=prev["module"], target=prev["target"],
            severity=_Sev.INFO, message=prev["error"],
        ))

    fixed = 0
    escalated = 0
    for f in findings:
        row = memory.record(f.module, f.target, f.message)
        fp = row["fingerprint"]
        if memory.should_skip(fp, cooldown_seconds=300):
            continue
        if f.severity < Severity.ERROR:
            continue

        # Tier 1
        if cfg.agent.fixer.tier1_rules and f.fix_hint:
            result = await tier1_rules.try_fix(f, services)
            if result and result.get("ok"):
                memory.mark_fix_attempt(fp, tier=1)
                fixed += 1
                continue

        # Tier 2
        if cfg.agent.fixer.tier2_small_llm:
            decision = await tier2_small.attempt_fix(cfg, f, services, http)
            memory.mark_fix_attempt(fp, tier=2)
            if decision.get("action") in ("restart", "no_op") and (
                decision.get("action") == "no_op"
                or (decision.get("restart_result") or {}).get("ok")
            ):
                fixed += 1
                continue

        # Tier 3
        if cfg.agent.fixer.tier3_smart_llm:
            try:
                fixer = SmartFixer(cfg, http)
                result = await fixer.attempt_fix(f)
                memory.mark_fix_attempt(fp, tier=3)
                if result.get("ok"):
                    fixed += 1
                    continue
            except Exception as e:
                logger.exception("tier-3 raised: %s", e)

        # Nothing fixed this — escalate and notify.
        escalated += 1
        await notifier.publish(f, action_taken="escalated to human")

    elapsed = time.time() - started
    summary = {
        "duration_s": round(elapsed, 1),
        "findings": len(findings),
        "fixed": fixed,
        "escalated": escalated,
        "open_failures": len(memory.open_failures()),
    }
    logger.info("scan complete: %s", summary)
    return summary


async def scan_once(cfg: Config) -> int:
    """Run a single scan and exit."""
    from homelab_ai.services import load_services

    if not cfg.agent.enabled:
        logger.info("agent disabled in config")
        return 0

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        services = load_services(cfg, http)
        modules = _load_modules(cfg, services)
        memory = FailureMemory(Path("./data") / "agent.db")
        try:
            await _do_scan(modules, memory, services, http, cfg)
        finally:
            memory.close()
    return 0


async def run_forever(cfg: Config) -> None:
    """Long-running scan loop."""
    from homelab_ai.services import load_services

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        services = load_services(cfg, http)
        modules = _load_modules(cfg, services)
        memory = FailureMemory(Path("./data") / "agent.db")
        logger.info("agent started with %d modules, %d services, %ds interval",
                    len(modules), len(services), cfg.agent.scan_interval)
        try:
            while True:
                await _do_scan(modules, memory, services, http, cfg)
                await asyncio.sleep(cfg.agent.scan_interval)
        finally:
            memory.close()
