# HTTP API reference

The full OpenAPI spec is served at `/openapi.json` and rendered at `/docs`. This page covers the endpoints you'll touch most often.

## Health

```
GET  /api/health             → {"ok": true, "version": "0.1.0"}
GET  /api/overview           → {"<service>": {"ok": bool, ...}, ...}
```

## Services

```
GET  /api/services                   → {"count": N, "services": ["sonarr", ...]}
GET  /api/services/{name}/health     → {"ok": bool, ...}
POST /api/services/{name}/restart    → {"ok": bool, "detail": "..."}
```

## Agent

```
GET  /api/agent/status      → {"running": bool, "open_failures": N, "recent": [...]}
POST /api/agent/scan        → {"ok": true, "detail": "scan started"}
```

## AI

```
GET  /api/ai/tools                → {"tools": [...]}
POST /api/ai/agent                → {"answer": "...", "tool_calls": [...]}
POST /api/ai/agent/stream         → SSE stream of {"type": "...", ...}
```

Body: `{"prompt": "..."}`.

## Settings

```
GET  /api/settings           → the overlay settings YAML, as JSON
PUT  /api/settings           → save the overlay (full document replace)
```

## MCP

If the `mcp` extra is installed:

```
GET  /mcp                    → MCP protocol endpoint (stdio adapter at /mcp/stdio)
GET  /mcp/tools              → JSON dump of the MCP tool catalog
```

Wire `http://homelab-ai:9105/mcp` into Claude Desktop's `mcpServers` config or Open WebUI's tool servers.

## Example session

```bash
# What services are configured?
curl http://localhost:9105/api/services

# Are any unhealthy right now?
curl http://localhost:9105/api/overview | jq 'to_entries[] | select(.value.ok==false)'

# Ask the AI agent
curl -XPOST http://localhost:9105/api/ai/agent \
    -H 'Content-Type: application/json' \
    -d '{"prompt": "Is anything broken right now? If so what would you try?"}'

# Trigger a fresh agent scan
curl -XPOST http://localhost:9105/api/agent/scan
```
