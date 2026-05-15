"""Abstract LLM client interface.

Two implementations:
- OllamaClient (native /api/chat — supports `think=False`, keep_alive)
- OpenAICompatClient (POST /v1/chat/completions — works with OpenAI,
  Anthropic, vLLM, LiteLLM, OpenRouter, LM Studio, Groq, Together, and
  Ollama's own /v1 compatibility layer)

Both speak tool calling. Pick one in config:

    llm:
      backend: openai_compat        # or "ollama" or "auto"
      url: http://localhost:11434/v1
      api_key: ${OPENAI_API_KEY}    # optional
      small_model: qwen3.5:4b
      smart_model: qwen3.6:35b-a3b
      embed_model: nomic-embed-text
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class LLMClient(Protocol):
    """Interface every backend implements."""

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict | AsyncIterator[dict]:
        """Return a chat response. On stream=True, return an async iterator of chunks.

        Tools follow the OpenAI function-calling schema. Both backends accept
        the same shape; the implementation translates as needed.
        """
        ...

    async def embed(self, model: str, text: str) -> list[float]:
        """Return an embedding vector."""
        ...

    async def list_models(self) -> list[dict]:
        """Return loaded/available models — at minimum `[{"name": ...}, ...]`."""
        ...
