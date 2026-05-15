"""Thin async client for the Ollama REST API.

Wraps `/api/chat` (with tools), `/api/embeddings`, `/api/tags`. The full
client is intentionally small — Ollama's API is straightforward and we'd
rather have one obvious file than a dependency on `ollama-python`.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

logger = logging.getLogger("homelab_ai.llm.ollama")


class OllamaClient:
    def __init__(self, url: str, http: aiohttp.ClientSession, keep_alive: str = "2m"):
        self.url = url.rstrip("/")
        self.http = http
        self.keep_alive = keep_alive

    async def list_models(self) -> list[dict]:
        async with self.http.get(f"{self.url}/api/tags") as r:
            r.raise_for_status()
            data = await r.json()
        return data.get("models", [])

    async def embed(self, model: str, text: str) -> list[float]:
        payload = {"model": model, "prompt": text, "keep_alive": self.keep_alive}
        async with self.http.post(f"{self.url}/api/embeddings", json=payload) as r:
            r.raise_for_status()
            data = await r.json()
        return data.get("embedding", [])

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        think: bool | None = None,
        options: dict | None = None,
    ) -> dict | AsyncIterator[dict]:
        """Call /api/chat. Returns one response dict (stream=False) or an
        async iterator of chunks (stream=True).
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools
        if think is not None:
            payload["think"] = think
        if options:
            payload["options"] = options

        if not stream:
            async with self.http.post(f"{self.url}/api/chat", json=payload) as r:
                r.raise_for_status()
                return await r.json()
        return self._stream_chat(payload)

    async def _stream_chat(self, payload: dict) -> AsyncIterator[dict]:
        async with self.http.post(f"{self.url}/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.content:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("ollama stream: non-JSON line: %s", line[:200])


def tool_to_openai_function(name: str, description: str, schema: dict) -> dict:
    """Convert a homelab-ai ToolSpec into the function-call shape Ollama
    accepts (matches OpenAI's function-calling schema)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema,
        },
    }
