"""OpenAI-compatible chat client.

Works with any backend that speaks the OpenAI API shape:
- OpenAI / Azure OpenAI
- Anthropic via LiteLLM proxy
- vLLM, sglang, llama.cpp server
- Ollama's `/v1` compatibility endpoint
- LM Studio
- OpenRouter, Groq, Together, Fireworks, Perplexity
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

logger = logging.getLogger("homelab_ai.llm.openai_compat")


class OpenAICompatClient:
    def __init__(
        self,
        url: str,
        http: aiohttp.ClientSession,
        api_key: str | None = None,
        keep_alive: str | None = None,
    ):
        # Allow both "http://x:8000" and "http://x:8000/v1" — normalize.
        url = url.rstrip("/")
        if not url.endswith("/v1"):
            url = url + "/v1"
        self.url = url
        self.http = http
        self.api_key = api_key
        self.keep_alive = keep_alive  # passed as extra body field if non-None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def list_models(self) -> list[dict]:
        async with self.http.get(f"{self.url}/models", headers=self._headers()) as r:
            r.raise_for_status()
            data = await r.json()
        return data.get("data") or data.get("models") or []

    async def embed(self, model: str, text: str) -> list[float]:
        payload = {"model": model, "input": text}
        async with self.http.post(
            f"{self.url}/embeddings", headers=self._headers(), json=payload
        ) as r:
            r.raise_for_status()
            data = await r.json()
        items = data.get("data") or []
        if not items:
            return []
        return items[0].get("embedding") or []

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        **_kwargs: Any,
    ) -> dict | AsyncIterator[dict]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": _normalize_messages(messages),
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if self.keep_alive is not None:
            # Ollama-flavoured backends honor this; OpenAI/others ignore it.
            payload["keep_alive"] = self.keep_alive

        if not stream:
            async with self.http.post(
                f"{self.url}/chat/completions", headers=self._headers(), json=payload
            ) as r:
                r.raise_for_status()
                data = await r.json()
            return _normalize_response(data)
        return self._stream(payload)

    async def _stream(self, payload: dict) -> AsyncIterator[dict]:
        async with self.http.post(
            f"{self.url}/chat/completions", headers=self._headers(), json=payload
        ) as r:
            r.raise_for_status()
            async for raw in r.content:
                line = raw.strip()
                if not line or not line.startswith(b"data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == b"[DONE]":
                    return
                try:
                    yield _normalize_chunk(json.loads(chunk))
                except json.JSONDecodeError:
                    logger.warning("openai_compat: bad SSE line: %r", chunk[:200])


def _normalize_messages(messages: list[dict]) -> list[dict]:
    """OpenAI requires tool messages carry tool_call_id; if upstream code
    didn't supply one we backfill with a stable hash so the API accepts it.
    Most providers are lenient; this is for stricter ones (Azure)."""
    out = []
    for i, m in enumerate(messages):
        if m.get("role") == "tool" and not m.get("tool_call_id"):
            m = dict(m)
            m["tool_call_id"] = f"call_{i}"
        out.append(m)
    return out


def _normalize_response(data: dict) -> dict:
    """Squash OpenAI's `choices[0].message` shape into the Ollama-style
    `{"message": {...}}` the rest of homelab-ai expects.
    """
    choices = data.get("choices") or []
    if not choices:
        return {"message": {"content": "", "tool_calls": []}}
    msg = choices[0].get("message", {})
    return {
        "message": {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content") or "",
            "tool_calls": msg.get("tool_calls") or [],
        },
        "model": data.get("model"),
    }


def _normalize_chunk(data: dict) -> dict:
    """Map a streaming `chunk.choices[0].delta` to {"message": {"content": ...}}."""
    choices = data.get("choices") or []
    if not choices:
        return {"done": True}
    delta = choices[0].get("delta", {})
    return {
        "message": {
            "role": delta.get("role", "assistant"),
            "content": delta.get("content") or "",
            "tool_calls": delta.get("tool_calls") or [],
        },
        "done": choices[0].get("finish_reason") is not None,
    }
