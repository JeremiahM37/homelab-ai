"""Rule engine — match Findings against config-defined triggers, run actions.

A rule is:

    {
      "name": "restart_sonarr_on_error",
      "trigger": {
        "type": "finding",          # currently only "finding"; "schedule"+ ahead
        "severity": "ERROR",        # optional — matched if Finding.severity >= this
        "module": "service_health", # optional — exact match
        "target": "sonarr",         # optional — exact match
        "fix_hint": "restart_service" # optional — exact match
      },
      "action": {
        "tool": "restart_service",
        "args": {"name": "{target}"}
      },
      "throttle_seconds": 300       # optional, default 300 — rule fires at most
                                    # once per (rule, target) per this window
    }

Templated args support `{target}`, `{module}`, `{severity}`, `{message}` from
the Finding. Unknown placeholders pass through literally.

The engine maintains an in-memory last-fired map keyed by (rule, target) so a
rapidly flapping finding doesn't fire the same rule on every scan.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homelab_ai.agent.modules import Finding

logger = logging.getLogger("homelab_ai.automations")

_SEV_RANK = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}


@dataclass
class Rule:
    name: str
    trigger: dict
    action: dict
    throttle_seconds: int = 300
    last_fired: dict[str, float] = field(default_factory=dict)


def matches(rule: Rule, finding: "Finding") -> bool:
    t = rule.trigger or {}
    if t.get("type", "finding") != "finding":
        return False
    if (sev := t.get("severity")) and \
            _SEV_RANK.get(finding.severity.name, 0) < _SEV_RANK.get(sev, 0):
        return False
    if (m := t.get("module")) and m != finding.module:
        return False
    if (tgt := t.get("target")) and tgt != finding.target:
        return False
    return not ((hint := t.get("fix_hint")) and hint != finding.fix_hint)


def render_args(template: dict, finding: "Finding") -> dict:
    """Substitute {target}, {module}, {severity}, {message} in arg values."""
    context = {
        "target": finding.target,
        "module": finding.module,
        "severity": finding.severity.name,
        "message": finding.message,
    }
    out = {}
    for k, v in (template or {}).items():
        if isinstance(v, str):
            try:
                out[k] = v.format(**context)
            except (KeyError, IndexError, ValueError):
                out[k] = v
        else:
            out[k] = v
    return out


class AutomationEngine:
    def __init__(self, rules: list[dict], services: dict):
        self.rules = [
            Rule(
                name=r.get("name", f"rule_{i}"),
                trigger=r.get("trigger") or {},
                action=r.get("action") or {},
                throttle_seconds=int(r.get("throttle_seconds", 300)),
            )
            for i, r in enumerate(rules)
        ]
        self.services = services
        # Pre-index tools so dispatch is O(1).
        self._tools = {}
        for svc in services.values():
            for spec in svc.tools():
                self._tools[spec.name] = spec

    async def on_finding(self, finding: "Finding") -> list[dict]:
        """Returns the list of rules that fired + their results."""
        now = time.time()
        fired = []
        for rule in self.rules:
            if not matches(rule, finding):
                continue
            key = finding.target or "_"
            last = rule.last_fired.get(key, 0)
            if now - last < rule.throttle_seconds:
                logger.debug("rule %s throttled for %s", rule.name, key)
                continue
            rule.last_fired[key] = now
            result = await self._fire(rule, finding)
            fired.append({"rule": rule.name, "result": result})
        return fired

    async def _fire(self, rule: Rule, finding: "Finding") -> dict:
        tool_name = rule.action.get("tool")
        spec = self._tools.get(tool_name)
        if not spec:
            logger.warning("automation %s references unknown tool %s",
                           rule.name, tool_name)
            return {"error": f"unknown tool {tool_name}"}
        args = render_args(rule.action.get("args") or {}, finding)
        try:
            result = await asyncio.wait_for(spec.handler(**args), timeout=60)
            logger.info("automation %s fired %s → %s", rule.name, tool_name, _short(result))
            return {"ok": True, "tool": tool_name, "result": result}
        except Exception as e:
            logger.warning("automation %s tool %s failed: %s", rule.name, tool_name, e)
            return {"error": f"{type(e).__name__}: {e}"}


def _short(x, n: int = 200) -> str:
    s = str(x)
    return s if len(s) <= n else s[:n] + "…"
