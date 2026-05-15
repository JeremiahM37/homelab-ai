"""LLM clients — pick a backend.

`get_client(cfg, http)` returns the right client based on `cfg.llm.backend`:

  llm:
    backend: openai_compat   # or "ollama", or "auto" (default)
    url: ...
    api_key: ...             # optional
    small_model: ...
    smart_model: ...
    embed_model: ...

"auto" prefers Ollama if the URL ends in :11434, else OpenAI-compat.

Legacy `ollama:` config block is honoured as a fallback so v0.1/v0.2 configs
keep working.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp

from .ollama import OllamaClient, tool_to_openai_function
from .openai_compat import OpenAICompatClient

if TYPE_CHECKING:
    from homelab_ai.config import Config

__all__ = ["OllamaClient", "OpenAICompatClient", "tool_to_openai_function", "get_client"]


def get_client(cfg: "Config", http: aiohttp.ClientSession):
    """Return the right LLM client for this config."""
    llm_block = (cfg._raw.get("llm") or {})
    legacy_ollama = (cfg._raw.get("ollama") or {})

    backend = llm_block.get("backend", "auto")
    url = llm_block.get("url") or legacy_ollama.get("url") or cfg.ollama.url
    api_key = llm_block.get("api_key") or legacy_ollama.get("api_key")
    keep_alive = llm_block.get("keep_alive", cfg.ollama.keep_alive)

    if backend == "auto":
        # Heuristic: Ollama's default port is 11434 and is /api/* not /v1.
        backend = "ollama" if (":11434" in url and "/v1" not in url) else "openai_compat"

    if backend == "ollama":
        return OllamaClient(url, http, keep_alive=keep_alive or "2m")
    if backend == "openai_compat":
        return OpenAICompatClient(url, http, api_key=api_key, keep_alive=keep_alive)
    raise ValueError(f"unknown llm.backend: {backend!r}")


def get_model(cfg: "Config", tier: str = "small") -> str:
    """Return the model name for the given tier ('small', 'smart', 'embed').

    Reads cfg.llm.* first, falls back to cfg.ollama.* (legacy).
    """
    llm_block = (cfg._raw.get("llm") or {})
    legacy = (cfg._raw.get("ollama") or {})
    key = {
        "small": "small_model",
        "smart": "smart_model",
        "embed": "embed_model",
    }[tier]
    return llm_block.get(key) or legacy.get(key) or getattr(cfg.ollama, key)
