"""Config loader — YAML file + env-var overrides via ${VAR} syntax.

All configuration goes through `Config`. Plugins receive their own slice as
`config["url"]`, `config["api_key"]`, etc. — no global state.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ${ENV_VAR} references in strings."""
    if isinstance(value, str):
        return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 9105
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class OllamaConfig:
    url: str = "http://localhost:11434"
    small_model: str = "qwen3.5:4b"
    smart_model: str = "qwen3.6:35b-a3b"
    keep_alive: str = "2m"


@dataclass
class FixerConfig:
    tier1_rules: bool = True
    tier2_small_llm: bool = True
    tier3_smart_llm: bool = True
    backup_dir: str = "./data/backups"
    audit_log: str = "./data/audit_log.md"
    max_files_changed_per_fix: int = 5
    max_lines_changed_per_fix: int = 200


@dataclass
class NotifyConfig:
    discord_webhook: str = ""
    generic_webhook: str = ""
    rate_limit_per_hour: int = 20


@dataclass
class AgentConfig:
    enabled: bool = True
    scan_interval: int = 300
    modules: list[str] = field(default_factory=lambda: ["container_doctor", "service_health"])
    fixer: FixerConfig = field(default_factory=FixerConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)


@dataclass
class MCPConfig:
    enabled: bool = True
    gated_tools: list[str] = field(default_factory=list)


@dataclass
class SettingsStore:
    store_path: str = "./data/settings.yaml"


@dataclass
class VerifyConfig:
    groups: list[str] = field(default_factory=lambda: ["core", "services", "ai"])
    fix_request_path: str = "./data/fix-request.md"


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    settings: SettingsStore = field(default_factory=SettingsStore)
    verify: VerifyConfig = field(default_factory=VerifyConfig)
    services: dict[str, dict] = field(default_factory=dict)
    # Original parsed dict — preserved so plugins can pick up keys we don't
    # know about at the dataclass level.
    _raw: dict = field(default_factory=dict)

    def service(self, name: str) -> dict | None:
        return self.services.get(name)


def load_config(path: Path | str = "config.yaml") -> Config:
    path = Path(path)
    if not path.is_file():
        # First-run fallback — return defaults so `homelab-ai run` works
        # even without a config file (no services, agent disabled).
        cfg = Config()
        cfg.agent.enabled = False
        return cfg

    with path.open() as f:
        raw = yaml.safe_load(f) or {}

    raw = _expand_env(raw)

    cfg = Config()
    cfg._raw = raw

    if s := raw.get("server"):
        cfg.server = ServerConfig(**{k: v for k, v in s.items() if hasattr(ServerConfig, k)})
    if o := raw.get("ollama"):
        cfg.ollama = OllamaConfig(**{k: v for k, v in o.items() if hasattr(OllamaConfig, k)})
    if a := raw.get("agent"):
        fixer = FixerConfig(**(a.get("fixer") or {}))
        notify = NotifyConfig(**(a.get("notify") or {}))
        cfg.agent = AgentConfig(
            enabled=a.get("enabled", True),
            scan_interval=a.get("scan_interval", 300),
            modules=a.get("modules") or ["container_doctor", "service_health"],
            fixer=fixer,
            notify=notify,
        )
    if m := raw.get("mcp"):
        cfg.mcp = MCPConfig(**{k: v for k, v in m.items() if hasattr(MCPConfig, k)})
    if v := raw.get("verify"):
        cfg.verify = VerifyConfig(**{k: v for k, v in v.items() if hasattr(VerifyConfig, k)})
    if s := raw.get("settings"):
        cfg.settings = SettingsStore(**{k: v for k, v in s.items() if hasattr(SettingsStore, k)})

    cfg.services = raw.get("services") or {}

    return cfg
