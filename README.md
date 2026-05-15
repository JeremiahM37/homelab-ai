# homelab-ai

> Self-hosted AI orchestrator for your homelab — monitors your services, self-heals when they break, and exposes everything you run as MCP tools any LLM can drive.

[![CI](https://github.com/JeremiahM37/homelab-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/JeremiahM37/homelab-ai/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/homelab-ai)](https://pypi.org/project/homelab-ai/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io%2FJeremiahM37%2Fhomelab--ai-blue)](https://github.com/JeremiahM37/homelab-ai/pkgs/container/homelab-ai)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Self-hosted](https://img.shields.io/badge/self--hosted-yes-green.svg)](https://github.com/awesome-selfhosted/awesome-selfhosted)

A FastAPI + Ollama-powered control plane that sits in front of your *arr stack, Jellyfin, qBittorrent, Paperless, Immich, Home Assistant — whatever you run — and gives you:

- **Proactive monitoring** with a plugin-based agent loop and SQLite failure memory (no alert spam, no flapping fixes).
- **3-tier auto-repair**: cheap rule checks → small LLM with safe tools → big LLM with file edits, full audit log, backups before every change.
- **A single AI agent** (Ollama, OpenAI-compatible, anything that speaks tool-calling) that can drive every service through one HTTP surface.
- **MCP server** so Claude Desktop, Open WebUI, Cursor, or any MCP client can plug into your homelab natively.
- **Mobile PWA** with chat, dashboard, and per-service deep links — installable, works on LAN or over Tailscale.
- **No vendor lock-in**: local-first, your data and credentials stay on your hardware.

> **Status:** beta. The core architecture is stable and battle-tested in a production homelab; expect rough edges around new-service plugins and the PWA polish.

---

## Why this exists

The selfhosted scene has great *individual* tools — Sonarr knows about TV, Immich knows about photos, Paperless knows about scans — but nothing that lets an LLM **drive all of them coherently**. You can ask ChatGPT for a recipe; you can't ask your homelab "is anything broken, and if so fix it" or "find me an audiobook by Brandon Sanderson and download it" without writing custom glue per service.

homelab-ai is the glue: a config-driven plugin system where every service you run becomes both a monitored entity *and* a callable tool, with an AI agent that does the routing and an auto-repair loop that fixes the boring stuff while you sleep.

---

## Quick start

**Recommended — Docker:**

```bash
# 1) Generate config.yaml interactively (detects Ollama, scans for services, makes an API key)
docker run --rm -it --network host -v "$PWD/data:/data" \
    ghcr.io/jeremiahm37/homelab-ai:latest --config /data/config.yaml init

# 2) Run for real
docker run -d --name homelab-ai \
    -p 9105:9105 \
    -v "$PWD/data:/data" \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    ghcr.io/jeremiahm37/homelab-ai:latest
```

Open `http://<your-host>:9105/app`. The PWA asks for the API key on first load — paste it from `data/config.yaml`.

Or use [docker-compose.example.yml](docker-compose.example.yml).

**Try with zero setup — demo mode:**

```bash
docker run --rm -p 9105:9105 ghcr.io/jeremiahm37/homelab-ai:latest demo
```

Open `http://localhost:9105/app` — five mock services, working chat with tool-call cards, real history, no Ollama needed.

**Python install (for development or running as a systemd service):**

```bash
pip install homelab-ai
homelab-ai --config config.yaml init
homelab-ai --config config.yaml run
```

The pip path is mainly for contributors and people running homelab-ai as a host-level systemd service. For day-to-day self-hosting, use Docker — dependency isolation, single-command upgrades, and the only thing you need to back up is `./data`.

### LLM backend — bring your own

Works with anything that speaks the Ollama or OpenAI API:

```yaml
llm:
  backend: openai_compat            # or "ollama", or "auto"
  url: https://api.openai.com/v1    # or http://localhost:11434 for Ollama
  api_key: ${OPENAI_API_KEY}
  small_model: gpt-4o-mini
  smart_model: gpt-4o
  embed_model: text-embedding-3-small
```

Tested with Ollama, vLLM, LiteLLM proxy, OpenAI, Anthropic-via-LiteLLM, OpenRouter, Groq, LM Studio.

### Auth

Set `auth.enabled: true` in `config.yaml` (the wizard does this for you) and every request needs an `X-Api-Key` header or a session cookie. Optional username/password users go in `auth.users` with bcrypt hashes (or PBKDF2 if `bcrypt` isn't installed).

```yaml
auth:
  enabled: true
  api_key: hk_<generated-32-char-token>
  users:
    admin: "$2b$12$..."
```

### Modular features

Everything beyond the agent/AI core is opt-in. Toggle features in `config.yaml`:

```yaml
features:
  metrics: {enabled: true}              # /metrics endpoint
  ntfy: {enabled: true, url: "..."}     # push notifications
  scheduler: {enabled: true, schedules: [...]}
  webhooks: {enabled: true, receivers: {...}}
  multi_llm: {enabled: true, ...}       # cheap local + paid for hard problems
  history: {enabled: true}              # /api/history/{scans,ai,fixes}
  rag: {enabled: true}                  # ChromaDB-backed document search
  mcp_http: {enabled: true}             # /mcp JSON-RPC for HTTP MCP clients
```

A feature that's off has zero cost — its module is never imported, its routes are never registered, its deps don't need to be installed. Heavy deps live behind pip extras:

```bash
pip install homelab-ai[metrics]    # adds prometheus-client
pip install homelab-ai[rag]        # adds chromadb
pip install homelab-ai[scheduler]  # adds croniter
pip install homelab-ai[all]        # everything
```

See [docs/features.md](docs/features.md) for the full menu.

---

## What it looks like

```
┌─────────────────────────────────────────────────────────┐
│ Mobile PWA   /  AI Chat   /  MCP Client (Claude/etc.)   │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP + tool calls
┌─────────────────────▼───────────────────────────────────┐
│        FastAPI core  (REST, MCP, WebUI, Settings)       │
│        │              │                  │              │
│        ▼              ▼                  ▼              │
│   Tool router    Service plugins    Settings store      │
│   (semantic)    (Sonarr, Radarr,   (YAML + secrets)    │
│                  Jellyfin, ...)                         │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│  Agent scan loop  ──►  Tier-1 rules  ──►  Tier-2 LLM    │
│                                            │            │
│  Failure memory (SQLite) ◄─────────────────┘            │
│                                            │            │
│                                            ▼            │
│                                       Tier-3 smart      │
│                                       fixer + audit     │
└─────────────────────────────────────────────────────────┘
```

---

## Features

### Agent & auto-repair
- Pluggable scan modules (container health, disk, services). Add a class, drop it in `agent/modules/`, done.
- SQLite failure memory: same error doesn't fire the same fix twice in a row.
- **Tier 1** — rule-based fixes (restart container, clear cache, retry indexer).
- **Tier 2** — small LLM (≈4B params) with a limited tool catalog: enough to investigate logs and call repair tools, not enough to delete things.
- **Tier 3** — smart fixer with a bigger model (≈30B). Can read/write files, but **every edit is backed up to `backups/` and logged in `audit_log.md`** for human review.
- The agent **never** pushes to remote git, posts to social, or runs destructive commands without a config flag set by the operator.

### AI surface
- One agent endpoint (`/api/ai/agent`) that picks tools semantically and streams responses.
- Built-in tools for the popular *arr stack, qBittorrent/Transmission/SABnzbd, Jellyfin/Plex, Immich, Paperless, Ollama.
- Drop a Python file in `mcp/custom_tools/` to add your own.
- Tool descriptions are embedded once at startup; the router picks the smallest relevant set per query (no 50-tool wall slowing every prompt).

### Service plugins
- Each service is one class with `health()`, `restart()`, and optional `tools()` methods.
- The agent uses `health()` for monitoring; the AI uses `tools()` for actions.
- Built-in plugins cover the common *arr stack — see [docs/adding-services.md](docs/adding-services.md) to wire in anything that has an HTTP API.

### Mobile PWA
- Installable, works on LAN or Tailscale.
- Live dashboard, AI chat, per-service status, settings editor.
- No login by default — put it behind your existing reverse proxy / SSO (Authelia, Caddy basic-auth, Cloudflare Access).

### Verification
- `python -m homelab_ai.verify` runs a flow-test suite against your live config.
- Failures write a `fix-request.md` file the AI agent or you can pick up.
- Use it as a nightly systemd timer or a pre-deploy gate.

---

## Configuration

All configuration lives in **one** `config.yaml`. Environment variables override file values, so secrets can stay out of the file. See [config.example.yaml](config.example.yaml) for the annotated reference.

Minimal example:

```yaml
ollama:
  url: http://localhost:11434
  small_model: qwen3.5:4b    # tool-calling / intent
  smart_model: qwen3.6:35b   # repair / chat

agent:
  scan_interval: 300         # seconds
  notify:
    discord_webhook: ""      # optional

services:
  sonarr:
    url: http://sonarr:8989
    api_key: ${SONARR_API_KEY}
  radarr:
    url: http://radarr:7878
    api_key: ${RADARR_API_KEY}
  jellyfin:
    url: http://jellyfin:8096
    api_key: ${JELLYFIN_API_KEY}
```

Service entries map to plugins by name. Unknown names are loaded from `homelab_ai/services/` or the user `~/.config/homelab-ai/services/` directory.

---

## Adding any service (no code)

For any service that speaks HTTP-JSON, you can add support **without writing Python** — just a config block:

```yaml
services:
  my_thing:
    plugin: generic_http
    url: http://my-thing:8080
    auth:
      type: bearer
      key: ${MY_THING_TOKEN}
    health:
      path: /healthz
    tools:
      - name: list_widgets
        description: List widgets from My Thing.
        path: /api/widgets
        params:
          limit: {type: integer, default: 10}
      - name: get_widget
        description: Get one widget by ID.
        path: /api/widgets/{id}
        params:
          id: {type: string, required: true, in: path}
```

Restart, and the agent monitors `my_thing` health every scan while the AI gains two new tools. See [docs/declarative-services.md](docs/declarative-services.md) for the full schema.

The 30 built-in Python plugins (sonarr, radarr, jellyfin, nut, etc.) remain the *finished build* — they handle wire protocols, multi-step auth, and complex transforms. `generic_http` is the *blueprint* for everything else.

## Adding a Python plugin (for cases generic_http can't handle)

```python
# ~/.config/homelab-ai/services/my_thing.py
from homelab_ai.services.base import Service, ToolSpec

class MyThing(Service):
    name = "my_thing"

    async def health(self) -> dict:
        r = await self.http.get(f"{self.config['url']}/health")
        return {"ok": r.status == 200}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="my_thing_status",
                description="Get current status of My Thing.",
                handler=self._status,
                params={},
            ),
        ]

    async def _status(self) -> dict:
        r = await self.http.get(f"{self.config['url']}/status")
        return await r.json()
```

Add to `config.yaml`:

```yaml
services:
  my_thing:
    url: http://my-thing:8080
```

Restart. The agent will start monitoring it; the AI will gain a `my_thing_status` tool.

Full guide: [docs/adding-services.md](docs/adding-services.md).

---

## Adding your own tool (no service)

If you just want to expose a function to the AI without wiring up a whole service:

```python
# ~/.config/homelab-ai/tools/weather.py
from homelab_ai.mcp.decorators import tool

@tool(description="Get the current temperature for a city.")
async def get_weather(city: str) -> dict:
    ...
```

Full guide: [docs/adding-tools.md](docs/adding-tools.md).

---

## API overview

| Endpoint | Purpose |
|----------|---------|
| `GET  /api/health` | Liveness probe |
| `GET  /api/overview` | All-services snapshot for dashboards |
| `GET  /api/services` | List of configured services and their health |
| `POST /api/ai/agent` | One-shot agent call: prompt in, tool calls + answer out |
| `POST /api/ai/agent/stream` | Same, server-sent-events streaming |
| `GET  /api/agent/status` | Last scan, recent fixes, queued escalations |
| `POST /api/agent/scan` | Trigger an immediate scan |
| `GET  /api/settings` / `PUT /api/settings` | Read / update config (mirrored to disk) |
| `GET  /mcp` | MCP server endpoint (for Claude Desktop, Open WebUI, etc.) |
| `GET  /app` | Mobile PWA |
| `GET  /docs` | OpenAPI Swagger UI |

The full OpenAPI spec is at `/openapi.json`. The MCP tool catalog is at `/mcp/tools`.

---

## Comparison

|                              | homelab-ai | Home Assistant + LLM Vision | n8n + Ollama | Open WebUI alone |
|------------------------------|:----------:|:---------------------------:|:------------:|:----------------:|
| Native *arr / media plugins  | ✅         | ❌                          | manual       | ❌               |
| Auto-repair / self-healing   | ✅         | partial                     | manual       | ❌               |
| MCP server (Claude/Cursor)   | ✅         | ❌                          | ❌           | partial          |
| Mobile PWA out of the box    | ✅         | ✅                          | ❌           | ✅               |
| Local-first / no cloud calls | ✅         | ✅                          | ✅           | ✅               |
| Selfhosted-LLM-friendly      | ✅         | ✅                          | ✅           | ✅               |

Pick the one whose primitives match what you do most. homelab-ai's primitive is **"a service that's monitored *and* AI-callable"**, which is the right shape for media/storage/scan workflows. Home Assistant's primitive is "a device with state and triggers", which is the right shape for IoT.

---

## Roadmap

Tracked in [GitHub issues](https://github.com/JeremiahM37/homelab-ai/issues). Near-term focuses:

- More built-in service plugins (Home Assistant, AdGuard, Nextcloud, NUT)
- OpenAI-compatible LLM backend (not just Ollama)
- Web installer / config wizard for first-time users
- Optional remote-access tunnel templates (Tailscale, Cloudflare Tunnel)
- HA-style automation triggers ("when X then call tool Y")

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). TL;DR: discuss large changes in an issue first; new services and tools should be plugins, not core patches; no personal IPs or secrets in code.

## License

[MIT](LICENSE).
