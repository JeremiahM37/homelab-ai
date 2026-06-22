"""Visibility tiers for RAG content.

Every ingested document carries a tier; every query is capped at a maximum
tier. Surfaces (the API, MCP, a chat widget, a public bot) map to a cap, so
sensitive content never reaches a less-trusted surface even though it all lives
in one collection.
"""
from __future__ import annotations

# Increasing sensitivity. A query capped at tier T may read tiers <= T.
TIERS: tuple[str, ...] = ("public", "lan", "admin")
_RANK = {t: i for i, t in enumerate(TIERS)}

# Sensible default cap per surface; override via features.rag.surface_tiers.
DEFAULT_SURFACE_TIERS: dict[str, str] = {
    "api": "admin",
    "mcp": "admin",
    "agent": "admin",
    "homepage": "lan",
    "pwa": "lan",
    "discord": "public",
    "public": "public",
}


def normalize_tier(tier: str | None, default: str = "lan") -> str:
    return tier if tier in _RANK else default


def allowed_tiers(max_tier: str) -> set[str]:
    cap = _RANK.get(max_tier, _RANK["admin"])
    return {t for t in TIERS if _RANK[t] <= cap}


def tiers_for_surface(surface: str, overrides: dict | None = None) -> set[str]:
    mapping = {**DEFAULT_SURFACE_TIERS, **(overrides or {})}
    return allowed_tiers(mapping.get(surface, "public"))
