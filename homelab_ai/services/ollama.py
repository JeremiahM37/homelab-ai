"""Ollama plugin — local LLM runtime. Doubles as the LLM backend for the AI."""
from __future__ import annotations

from .base import Service, ToolSpec


class Ollama(Service):
    name = "ollama"

    async def health(self) -> dict:
        try:
            tags = await self._get("/api/tags")
            models = tags.get("models", []) if isinstance(tags, dict) else []
            return {"ok": True, "model_count": len(models)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_models(self) -> dict:
        tags = await self._get("/api/tags")
        models = tags.get("models", []) if isinstance(tags, dict) else []
        return {
            "models": [
                {"name": m.get("name"), "size_gb": round((m.get("size") or 0) / 1e9, 1)}
                for m in models
            ],
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="ollama_list_models",
                description="List the LLM models loaded on the local Ollama server.",
                handler=self.list_models,
            ),
        ]
