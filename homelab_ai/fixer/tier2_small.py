"""Tier-2: small LLM with constrained tools — investigate + try safe repairs.

Tools available to Tier-2 (only — there is no file-edit capability here):
  - fetch_service_health(name) — call the service's health() method
  - restart_service(name)       — call the service's restart() method (Tier-1
                                  would have already tried; this is the
                                  "after looking at logs, retry the restart"
                                  branch).
  - list_services()             — names of currently configured services

Returns a decision dict:
  {"action": "restart", "service": "...", "rationale": "..."} or
  {"action": "no_op",   "rationale": "..."} or
  {"action": "escalate","rationale": "..."}

The fixer dispatcher in agent.loop picks up that decision and acts on it.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import aiohttp

from homelab_ai.llm.ollama import OllamaClient

if TYPE_CHECKING:
    from homelab_ai.agent.modules import Finding
    from homelab_ai.config import Config
    from homelab_ai.services.base import Service

logger = logging.getLogger("homelab_ai.fixer.tier2")


SYSTEM_PROMPT = """You are a homelab repair assistant invoked when a Tier-1
rule-based fix has failed or didn't apply. You can call a small set of read
tools and one safe write tool (restart). You CANNOT edit files.

Decide ONE of:
  - call restart_service(name) if the failure looks transient (timeout,
    connection refused, brief 5xx). Do this even if Tier-1 already tried —
    it may have raced.
  - return no_op if the service looks healthy now (transient already self-healed).
  - return escalate with a one-line reason if the failure looks like config
    drift, missing dependencies, or anything restart wouldn't fix.

Call at most 2 tools before deciding. Reply with raw JSON:
  {"action": "restart" | "no_op" | "escalate", "service": "...", "rationale": "..."}
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_service_health",
            "description": "Call the service's health() method and return the result dict.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Service name"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_services",
            "description": "Return the names of currently configured services.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def attempt_fix(
    cfg: Config,
    finding: Finding,
    services: dict[str, Service],
    http: aiohttp.ClientSession,
) -> dict:
    client = OllamaClient(cfg.ollama.url, http, cfg.ollama.keep_alive)

    async def _exec_tool(name: str, args: dict) -> dict:
        if name == "list_services":
            return {"services": list(services.keys())}
        if name == "fetch_service_health":
            svc = services.get(args.get("name", ""))
            if not svc:
                return {"error": "no such service"}
            try:
                return await svc.health()
            except Exception as e:
                return {"error": str(e)[:200]}
        return {"error": f"unknown tool {name!r}"}

    user_msg = (
        f"Failure detected by module={finding.module}, target={finding.target}.\n"
        f"Severity={finding.severity.name}. Message: {finding.message}\n"
        f"Context: {json.dumps(finding.context, default=str)[:500]}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    for _ in range(3):  # at most 3 LLM rounds
        try:
            resp = await client.chat(
                cfg.ollama.small_model,
                messages,
                tools=TOOL_SCHEMAS,
                stream=False,
                think=False,
            )
        except aiohttp.ClientError as e:
            logger.warning("tier-2 LLM unreachable: %s", e)
            return {"action": "escalate", "rationale": f"LLM unreachable: {e}"}

        msg = resp.get("message", {})
        calls = msg.get("tool_calls") or []
        if calls:
            messages.append(msg)
            for call in calls:
                fn = call.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = await _exec_tool(fn.get("name", ""), args)
                messages.append({"role": "tool", "content": json.dumps(result, default=str)})
            continue

        text = (msg.get("content") or "").strip()
        decision = _parse_decision(text)
        decision.setdefault("service", finding.target)
        logger.info("tier-2 decision for %s: %s", finding.target, decision.get("action"))

        # Execute the restart if that's the decision — caller doesn't have
        # to re-route through Tier-1 again.
        if decision.get("action") == "restart":
            svc = services.get(decision["service"])
            if svc:
                try:
                    result = await svc.restart()
                    decision["restart_result"] = result
                except Exception as e:
                    decision["restart_result"] = {"ok": False, "error": str(e)}
        return decision

    return {"action": "escalate", "rationale": "tier-2 exhausted tool budget"}


def _parse_decision(text: str) -> dict:
    """LLMs sometimes wrap JSON in markdown fences. Strip + parse permissively."""
    s = text.strip()
    if s.startswith("```"):
        # Drop opening + closing fence.
        s = s.split("\n", 1)[-1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    s = s.strip()
    try:
        d = json.loads(s)
        if isinstance(d, dict) and d.get("action") in ("restart", "no_op", "escalate"):
            return d
    except json.JSONDecodeError:
        pass
    return {"action": "escalate", "rationale": f"unparseable response: {text[:200]}"}
