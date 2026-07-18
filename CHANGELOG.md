# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`data_dir` setting** — agent state files (agent.db, notifier.json) now resolve through a single configurable directory (default `./data`, unchanged).
- **`agent.fixer.cooldown_seconds`** — the fix-retry cooldown (previously hardcoded to 300) is configurable.
- Scan summaries report an **`acknowledged`** count for Tier-2 `no_op` decisions ("already self-healed"), which are no longer counted as `fixed`.
- **Mullvad VPN plugin** — `services.mullvad` exposes read-only tools (`mullvad_status`, `mullvad_devices`, `mullvad_check_routing`) using only the 16-digit account number; the routing check catches "tunnel up but no traffic" black-holes.
- **RAG hybrid retrieval** — dense vectors + BM25 keyword search fused with Reciprocal Rank Fusion (`features.rag.hybrid`, on by default). BM25 needs `rank-bm25` (now in the `[rag]` extra); without it, retrieval degrades cleanly to dense-only.
- **RAG optional LLM rerank** — `features.rag.rerank` reorders fused candidates with a small model (`features.rag.rerank_model`, falls back to `llm.model`).
- **RAG incremental indexing** — a content-hash manifest skips unchanged sources and prunes stale chunks; re-ingesting identical content via `/api/rag/ingest` is now a no-op (`{"skipped": true}`).
- **RAG visibility tiers** — every document carries a `public`/`lan`/`admin` tier; `/api/rag/search` accepts `max_tier` or a `surface` (capped via `features.rag.surface_tiers`) so sensitive content never reaches a less-trusted surface.
- **Structure-aware chunking** for RAG — splits on Markdown headings / paragraphs instead of fixed-width cuts.

### Changed
- **Breaking**: `server.cors_origins` now defaults to `[]` (same-origin only) instead of `"*"`. The bundled PWA is unaffected; deployments serving a separate browser frontend must list its origin explicitly.
- `[rag]` extra now also installs `rank-bm25`.
- `/api/rag/ingest` now prunes a source's prior chunks before writing new ones (fixes stale chunks lingering when a document shrinks).

## [0.6.0] - 2026-05-15

### Added
- **PWA streaming chat** — consumes `/api/ai/agent/stream` SSE and renders tool calls live as cards.
- **PWA Config tab** — section-by-section form editor backed by `/api/config/{schema,current,save}`, with secrets preserved when blank.
- **PWA History tab** — three sub-tabs (Scans / AI calls / Fixes) reading `/api/history/*`, click-to-expand for full payload.
- **Chat history persistence** in localStorage (bounded to 50 turns) so refreshing the tab doesn't wipe the conversation.
- **`homelab-ai demo` subcommand** — boots the full server against five fake services so you can try every feature with no setup.
- **`homelab-ai status` subcommand** — probes `/api/health`, exits 0 if healthy. Useful for systemd / cron.
- **Declarative `generic_http` service plugin** — add any HTTP-JSON service as a YAML block (no Python required). Built-in plugins remain for wire-protocol services.
- **Six new builtin plugins**: tdarr, calibre-web, gluetun, changedetection, n8n, grafana.
- **NUT service plugin** speaking the native TCP protocol.
- **Automation engine** — HA-style when-X-then-Y rules over Findings.
- **Anomaly detection** — hour-of-day z-score baselines.
- **Tunnel templates** for Tailscale + Cloudflare Tunnel under `deploy/tunnels/`.
- **GHCR + PyPI release workflow** triggered on `v*.*.*` tags.

### Changed
- README now leads with the Docker install path. The pip path is kept for contributors and systemd users.
- Bottom nav grew from 3 tabs to 5 (Home, Chat, Config, History, Settings).

### Fixed
- Discovery probe could hang if a connector ignored `aiohttp.ClientTimeout`; defends with `asyncio.wait_for` now.
- Agent module loader picked the first `AgentModule` subclass alphabetically when a file defined several; now prefers the one whose `.name` matches.
- Anomaly detector skipped values when the baseline stddev was 0 — exactly when deviations are most anomalous. Constant-baseline case now flags with ±∞ z-score.

### Added
- Initial public release.
- YAML-driven config with environment-variable overrides.
- Agent scan loop with plugin module system.
- 3-tier repair: rules → small-LLM-with-tools → smart-LLM-with-file-edits + audit log.
- FastAPI HTTP layer with REST + MCP tool surface.
- Semantic tool routing — picks the smallest relevant tool set for each prompt.
- Mobile PWA shell with AI chat and live service status.
- Built-in service plugins for Sonarr, Radarr, Jellyfin, qBittorrent, Ollama.
- Verification framework with fix-request handoff for self-healing.
