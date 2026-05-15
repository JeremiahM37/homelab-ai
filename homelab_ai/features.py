"""Feature flags + capability detection.

The principle: every feature is **off by default**. Enabling a feature in
config.yaml is what brings its code path into play; if a feature is off,
its module is never imported and its dependencies don't need to be
installed.

Heavy deps (chromadb, prometheus-client) are gated behind pip extras:

    pip install homelab-ai[metrics]   # adds prometheus-client
    pip install homelab-ai[rag]       # adds chromadb

`Features.from_config(cfg)` reads `features:` from config.yaml. Anything
not in the file stays at its safe default (off).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homelab_ai.config import Config


@dataclass
class MetricsFeature:
    enabled: bool = False
    path: str = "/metrics"


@dataclass
class EmailFeature:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: list[str] = field(default_factory=list)
    use_tls: bool = True


@dataclass
class NtfyFeature:
    """Push notifications via ntfy.sh-style HTTP POST."""
    enabled: bool = False
    url: str = ""              # full URL including topic, e.g. https://ntfy.sh/mytopic
    token: str = ""            # optional access token
    priority: str = "default"  # min | low | default | high | max


@dataclass
class GotifyFeature:
    enabled: bool = False
    url: str = ""              # base URL of the gotify server
    token: str = ""            # app token


@dataclass
class SchedulerFeature:
    enabled: bool = False
    schedules: list[dict] = field(default_factory=list)
    # each schedule: {name, cron, tool, args, notify (optional)}


@dataclass
class WebhooksFeature:
    enabled: bool = False
    # Map of {name: {secret, tool, args_template}}
    receivers: dict[str, dict] = field(default_factory=dict)


@dataclass
class MultiLLMFeature:
    """Split small (intent / tools) and smart (chat / repair) across backends."""
    enabled: bool = False
    small_backend: str = ""    # "ollama" or "openai_compat"
    small_url: str = ""
    small_api_key: str = ""
    small_model: str = ""
    smart_backend: str = ""
    smart_url: str = ""
    smart_api_key: str = ""
    smart_model: str = ""
    # Optional cost tracking: counts requests per backend in memory.
    track_calls: bool = False


@dataclass
class HistoryFeature:
    enabled: bool = False
    db_path: str = "./data/history.db"
    keep_days: int = 30


@dataclass
class RAGFeature:
    enabled: bool = False
    chroma_path: str = "./data/chroma"
    embed_model: str = "nomic-embed-text"
    chunk_size: int = 800
    chunk_overlap: int = 100
    # Optional source plugins to index: ["paperless", "files", "url"]
    sources: list[str] = field(default_factory=list)


@dataclass
class MCPHttpFeature:
    enabled: bool = False
    path: str = "/mcp"


@dataclass
class Features:
    metrics: MetricsFeature = field(default_factory=MetricsFeature)
    email: EmailFeature = field(default_factory=EmailFeature)
    ntfy: NtfyFeature = field(default_factory=NtfyFeature)
    gotify: GotifyFeature = field(default_factory=GotifyFeature)
    scheduler: SchedulerFeature = field(default_factory=SchedulerFeature)
    webhooks: WebhooksFeature = field(default_factory=WebhooksFeature)
    multi_llm: MultiLLMFeature = field(default_factory=MultiLLMFeature)
    history: HistoryFeature = field(default_factory=HistoryFeature)
    rag: RAGFeature = field(default_factory=RAGFeature)
    mcp_http: MCPHttpFeature = field(default_factory=MCPHttpFeature)

    @classmethod
    def from_config(cls, cfg: "Config") -> "Features":
        raw = cfg._raw.get("features") or {}
        f = cls()
        for attr in ("metrics", "email", "ntfy", "gotify", "scheduler",
                     "webhooks", "multi_llm", "history", "rag", "mcp_http"):
            block = raw.get(attr) or {}
            if isinstance(block, bool):
                # shorthand: `features: {metrics: true}`
                block = {"enabled": block}
            target = getattr(f, attr)
            # `field(default_factory=...)` fields aren't class attributes,
            # so we enumerate via __dataclass_fields__ instead of hasattr.
            valid = set(type(target).__dataclass_fields__.keys())
            for k, v in block.items():
                if k in valid:
                    setattr(target, k, v)
        return f

    def summary(self) -> dict:
        return {
            attr: getattr(self, attr).enabled
            for attr in (
                "metrics", "email", "ntfy", "gotify", "scheduler",
                "webhooks", "multi_llm", "history", "rag", "mcp_http",
            )
        }


def has_capability(name: str) -> bool:
    """Best-effort check that an optional dep is importable.

    Used by feature modules at startup to fail clearly if a user enabled
    `metrics: true` without `pip install homelab-ai[metrics]`.
    """
    try:
        if name == "metrics":
            import prometheus_client  # noqa: F401
        elif name == "rag":
            import chromadb  # noqa: F401
        elif name == "croniter":
            import croniter  # noqa: F401
        else:
            return False
        return True
    except ImportError:
        return False
