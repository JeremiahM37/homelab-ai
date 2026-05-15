"""Boot homelab-ai with a config pointed at fake in-process services.

`homelab-ai demo` calls `run_demo()` here. We build a config with
auth.enabled=False (so users can poke at it without copy-pasting a key),
agent.enabled=True (so the agent loop runs and you can see findings flow),
and a stubbed AI client that returns canned responses (so it works without
Ollama).
"""
from __future__ import annotations

import logging
import sys

from homelab_ai.config import Config

logger = logging.getLogger("homelab_ai.demo")

_DEMO_BANNER = """
=======================================================================
  homelab-ai DEMO MODE — no real services, no Ollama required.
  Open http://localhost:9105/app in your browser.
  Auth is OFF so you can click around immediately.
  Stop with Ctrl-C.
=======================================================================
"""


def build_demo_config() -> Config:
    cfg = Config()
    cfg.server.host = "127.0.0.1"
    cfg.server.port = 9105
    cfg.auth.enabled = False
    cfg.agent.enabled = True
    cfg.agent.scan_interval = 30
    cfg.agent.modules = ["service_health"]
    cfg.services = {
        name: {"url": "http://demo-only", "_demo": True}
        for name in ("sonarr", "jellyfin", "qbittorrent", "ollama", "paperless")
    }
    # Show off the History + Config + MCP HTTP features in the PWA out of the box.
    cfg._raw = {
        "features": {
            "history": {"enabled": True, "db_path": "./data/demo_history.db"},
            "mcp_http": {"enabled": True},
            "config_editor": {"enabled": True, "config_path": "./data/demo_config.yaml"},
        }
    }
    return cfg


def _patch_loader_for_demo():
    """Override the service-registry resolver so config keys map to demo
    implementations instead of trying to load homelab_ai.services.<name>.
    """
    from homelab_ai.demo.fake_services import DEMO_SERVICES
    from homelab_ai.services import registry as _reg

    orig = _reg._resolve_plugin

    def _resolve(name: str):
        if name in DEMO_SERVICES:
            return DEMO_SERVICES[name]
        return orig(name)

    _reg._resolve_plugin = _resolve


def _patch_ai_for_demo():
    """Replace the agent_chat handler with a stub that returns canned answers
    + simulated tool calls, so the Chat tab works without Ollama installed.
    """
    from homelab_ai.api.routers import ai as ai_router

    async def _demo_loop(request, prompt, stream=False):
        # Cheap routing: pick a tool that matches a keyword in the prompt.
        services = request.app.state.services
        catalog = []
        for svc_name, svc in services.items():
            for spec in svc.tools():
                catalog.append({"service": svc_name, "spec": spec})
        prompt_lower = prompt.lower()
        chosen = []
        for entry in catalog:
            name = entry["spec"].name
            if any(tok in prompt_lower for tok in name.replace("_", " ").split()):
                chosen.append(entry)
        chosen = chosen[:2]

        tool_calls = []
        for entry in chosen:
            spec = entry["spec"]
            args = {}
            # Plug a sensible default for required params.
            for pname, pdef in spec.params.items():
                if isinstance(pdef, dict) and pdef.get("required"):
                    args[pname] = "demo"
            try:
                result = await spec.handler(**args)
            except Exception as e:
                result = {"error": str(e)}
            tool_calls.append({"name": spec.name, "arguments": args, "result": result})

        if not tool_calls:
            answer = (
                "Demo mode answer: I would normally call an LLM here, but this "
                "build is running without one. Try asking about Sonarr, Jellyfin, "
                "qBittorrent, Paperless, or Ollama and I'll wire up a tool call."
            )
        else:
            answer = "Demo response — tool results above. "\
                     "In a real install an LLM would summarize these for you."

        return {
            "answer": answer,
            "model": "demo-stub",
            "tool_calls": tool_calls,
            "iterations": 1,
        }

    ai_router._agent_loop = _demo_loop


def run_demo() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    print(_DEMO_BANNER, file=sys.stderr)
    _patch_loader_for_demo()
    _patch_ai_for_demo()
    cfg = build_demo_config()
    from homelab_ai.api.main import serve
    return serve(cfg)
