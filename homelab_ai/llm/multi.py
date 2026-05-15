"""Optional multi-LLM router.

Splits requests by tier:
- `small` requests (intent / tool routing) → cheap local model
- `smart` requests (chat / repair) → bigger / paid model

Off by default; enable with:

  features:
    multi_llm:
      enabled: true
      small_backend: ollama
      small_url: http://localhost:11434
      small_model: qwen3.5:4b
      smart_backend: openai_compat
      smart_url: https://api.openai.com/v1
      smart_api_key: ${OPENAI_API_KEY}
      smart_model: gpt-4o-mini
      track_calls: true     # in-memory counters for /metrics

When the feature is off the single-backend path from llm/__init__.py
applies — no extra code runs.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING

from .ollama import OllamaClient
from .openai_compat import OpenAICompatClient

if TYPE_CHECKING:
    import aiohttp

    from homelab_ai.features import MultiLLMFeature

logger = logging.getLogger("homelab_ai.llm.multi")


class MultiLLMRouter:
    """Holds two clients and routes by tier."""

    def __init__(self, feature: "MultiLLMFeature", http: "aiohttp.ClientSession"):
        self.cfg = feature
        self.http = http
        self.small = _build(feature.small_backend, feature.small_url,
                            feature.small_api_key, http)
        self.smart = _build(feature.smart_backend, feature.smart_url,
                            feature.smart_api_key, http)
        self._counts: Counter = Counter()

    def client_for(self, tier: str):
        """Return (client, model) for the requested tier."""
        if self.cfg.track_calls:
            self._counts[tier] += 1
        if tier == "small":
            return self.small, self.cfg.small_model
        if tier == "smart":
            return self.smart, self.cfg.smart_model
        # Default to small for unknown tiers.
        return self.small, self.cfg.small_model

    def call_counts(self) -> dict[str, int]:
        return dict(self._counts)


def _build(backend: str, url: str, api_key: str, http):
    if backend == "ollama":
        return OllamaClient(url, http)
    if backend == "openai_compat":
        return OpenAICompatClient(url, http, api_key=api_key)
    raise ValueError(f"unknown backend {backend!r} — use 'ollama' or 'openai_compat'")
