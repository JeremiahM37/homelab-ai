# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
