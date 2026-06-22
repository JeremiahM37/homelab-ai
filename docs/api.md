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

## RAG (optional)

Registered only when `features.rag.enabled`. Retrieval is hybrid (dense + BM25,
fused with RRF) with an optional LLM rerank; indexing is incremental; every
document carries a visibility tier (`public` / `lan` / `admin`).

```
POST   /api/rag/ingest        body: {source, text, metadata?, tier?}
                              → {source, chunks, tier} (or {skipped:true} if unchanged)
POST   /api/rag/search        body: {query, k?, source?, max_tier?, surface?}
                              → {results: [{text, source, chunk, tier, distance}, ...]}
GET    /api/rag/stats         → {chunks, sources, sources_by_tier, hybrid, rerank}
DELETE /api/rag/source/{src}  → {ok: true}
```

`tier` on ingest defaults to `features.rag.default_tier`. On search, `max_tier`
caps visibility directly; `surface` (e.g. `discord`) caps it via
`features.rag.surface_tiers`, so a public surface never sees `admin` content.

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
