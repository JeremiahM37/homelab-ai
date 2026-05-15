# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
