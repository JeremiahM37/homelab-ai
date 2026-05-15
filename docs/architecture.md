# Architecture

## Overview

homelab-ai is one process with three concurrent surfaces:

1. **FastAPI HTTP server** — serves the mobile PWA, the REST API, and the MCP-compatible tool catalog.
2. **Agent loop** — runs the configured scan modules on `agent.scan_interval`, surfaces findings, dispatches to the fixer.
3. **MCP server** (optional) — wraps the same tool catalog in MCP protocol so Claude Desktop, Open WebUI, and Cursor can drive your homelab natively.

All three share the same in-memory **service registry** populated at startup from `config.yaml`.

```
            ┌────────────────────────┐
            │      config.yaml       │
            └───────────┬────────────┘
                        │
        ┌───────────────▼───────────────┐
        │       Service Registry        │  Sonarr, Radarr, Jellyfin, ...
        │  (plugins discovered & init'd)│  (each: health/restart/tools)
        └─────┬─────────┬─────────┬─────┘
              │         │         │
   ┌──────────▼──┐ ┌────▼────┐ ┌──▼────────┐
   │ Agent loop  │ │ AI API  │ │ MCP server│
   │ (monitoring)│ │ (chat,  │ │ (Claude   │
   │             │ │ tools)  │ │ Desktop)  │
   └──────┬──────┘ └─────────┘ └───────────┘
          │
   ┌──────▼──────────────────────────┐
   │ 3-tier auto-repair               │
   │  Tier 1: rules                   │
   │  Tier 2: small LLM + safe tools  │
   │  Tier 3: smart LLM + file edits  │
   │   (audit log + file backups)     │
   └──────────────────────────────────┘
```

## Service plugins

A service is the unit of monitoring *and* AI exposure. Each plugin inherits from `homelab_ai.services.base.Service` and overrides:

| Method | Purpose | Used by |
|--------|---------|---------|
| `health() -> dict` | Lightweight liveness probe. Returns `{"ok": bool, ...}`. | Agent loop, `/api/overview` |
| `restart() -> dict` | Recover the service if `health()` is unhealthy. | Tier-1 fixer, `/api/services/{name}/restart` |
| `tools() -> list[ToolSpec]` | Functions to expose to the AI / MCP. | AI agent, MCP server |

Plugins are discovered by name. If `config.yaml` has `services.sonarr`, the loader looks for:
1. `homelab_ai/services/sonarr.py` (built-in).
2. `~/.config/homelab-ai/services/sonarr.py` (user override).
3. `$HOMELAB_AI_PLUGINS/sonarr.py` (custom dir).

The first match wins. The plugin reads its own config block — no global lookups.

## Agent loop

`homelab_ai/agent/loop.py:run_forever` instantiates the configured modules and runs them once per `scan_interval`. Each module returns a list of `Finding` objects. Findings flow into:

1. **Failure memory** — SQLite-backed dedup keyed by `(module, target, error_fingerprint)`. Same error inside the cooldown is a no-op.
2. **Fixer dispatch** — if a finding has a known `fix_hint`, Tier-1 takes a shot. If Tier-1 declines or fails, the finding escalates.
3. **Notifications** — alerts go out only after dedup. The 20/hour default prevents pager fatigue during flapping.

Add a new module by dropping a class in `homelab_ai/agent/modules/`:

```python
from .base import AgentModule, Finding, Severity

class MyModule(AgentModule):
    name = "my_module"

    async def scan(self) -> list[Finding]:
        # Your check logic here.
        return [Finding(
            module=self.name,
            target="something",
            severity=Severity.WARNING,
            message="something happened",
            fix_hint="restart_service",
        )]
```

Add `my_module` to `agent.modules` in config — done.

## 3-tier auto-repair

The fixer's job is to **fix small things before you wake up**, with progressively more capability but progressively more friction.

### Tier 1 — Rules

`homelab_ai/fixer/tier1_rules.py`. No LLM. Each rule is a function. The dispatcher matches `Finding.fix_hint` strings (`restart_service`, `restart_container`, `retry_indexer`, etc.) to handlers.

Tier 1 is **always safe**. Restarting a healthy container is a no-op; restarting a container in a crash loop is the right call. If a rule isn't a clear match, the rule returns None and the finding escalates.

### Tier 2 — Small LLM with safe tools

`homelab_ai/fixer/tier2_small.py`. A small (≈4B param) tool-calling model gets a constrained tool catalog:

- `fetch_logs(service, lines=100)` — read-only
- `list_services()` — read-only
- `restart_service(name)` — safe write
- `retry_job(service, job_id)` — safe write

It cannot edit files. Its job: look at the logs, decide whether a restart will fix this, and either call the right tool or escalate to Tier 3 with a one-sentence summary of what's broken.

### Tier 3 — Smart LLM with file edits

`homelab_ai/fixer/tier3_smart.py`. A larger (≈30B+) model that **can** edit files. Three hard safety properties:

1. **Snapshot first.** Every file the model wants to edit is copied to `backup_dir/` before the write. If the verify-suite re-run fails, the snapshot is restored.
2. **Audit every action.** `audit_log.md` gets a markdown entry with rationale, diff, and backup id for every change.
3. **Hard caps.** `max_files_changed_per_fix` and `max_lines_changed_per_fix` are enforced by the dispatcher, not the model. If the plan exceeds caps, the fix is refused.

The Tier-3 model is **not** allowed to push to git, post to external services, or delete files. These are enforced at the tool-spec level (the model literally doesn't have those tools).

## AI agent surface

`POST /api/ai/agent` is the single entry point. The handler:

1. Picks tools semantically via `SemanticToolRouter.select(query, k=8)`. Tool descriptions are embedded once at startup.
2. Hands the selected tools to the LLM client (default: Ollama tool-calling).
3. Executes tool calls, feeds results back, returns the answer.

Streaming via `POST /api/ai/agent/stream` with server-sent events.

## MCP server

`homelab_ai/mcp/server.py` builds an MCP server that exposes every tool the AI agent has. Drop the homelab-ai endpoint into Claude Desktop's `mcpServers` config and Claude can now drive your homelab directly.

The MCP catalog and the REST `/api/ai/agent` endpoint share the same tool registry — adding a new tool exposes it to both surfaces at once.

## Why one process

Most production-grade alternatives (Prometheus + Alertmanager + Karma + n8n + Open WebUI) need 5+ containers and a config of their own. homelab-ai bundles the monitoring + repair + AI surface in one process because:

- The dataflow is simple: scan → finding → fix → log. Splitting into services adds complexity without separating concerns.
- A failure in one stage shouldn't take down the others, but they should share state cheaply.
- One process = one set of secrets, one config file, one health check, one upgrade.

If you outgrow one process, the dataclass-based config and aiohttp service registry move cleanly to a worker queue. Don't refactor preemptively.
