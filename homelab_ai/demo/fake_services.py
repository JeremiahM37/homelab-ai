"""Stub service plugins that return plausible-looking data.

Each demo service inherits from `homelab_ai.services.base.Service` but
doesn't hit any network — it just returns hand-crafted data. The PWA,
the AI tools, the agent loop, /api/overview all work end-to-end against
these.
"""
from __future__ import annotations

import random
import time
from datetime import UTC, datetime, timedelta

from homelab_ai.services.base import Service, ToolSpec

# A tiny pool of plausible content so demos don't look canned. Seeded
# per-process so repeated calls stay consistent.
_BOOTED_AT = time.time()
_RAND = random.Random(42)


class _DemoBase(Service):
    """Skip the http session; demo services don't need it."""
    def __init__(self, config: dict, http=None):
        self.config = config
        self.http = http


class DemoSonarr(_DemoBase):
    name = "demo_sonarr"

    async def health(self) -> dict:
        return {"ok": True, "version": "4.0.17 (demo)", "health_issues": 0}

    async def queue(self) -> dict:
        return {"total": 3, "downloading": 2, "warning": 0,
                "items": [
                    {"title": "The Bear S03E04", "progress": 0.62},
                    {"title": "Foundation S02E09", "progress": 0.18},
                    {"title": "Severance S02E01", "progress": 0.04},
                ]}

    async def calendar(self, days: int = 7) -> dict:
        upcoming = [
            ("The Bear", "S03E05"), ("Foundation", "S02E10"),
            ("Severance", "S02E02"), ("For All Mankind", "S05E01"),
        ]
        out = []
        for i, (series, ep) in enumerate(upcoming):
            d = datetime.now(UTC) + timedelta(days=i + 1)
            out.append({"title": series, "name": ep, "air_date": d.isoformat()})
        return {"count": len(out), "upcoming": out}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="sonarr_queue", description="Current Sonarr download queue.",
                     handler=self.queue),
            ToolSpec(name="sonarr_calendar", description="Upcoming TV episodes.",
                     handler=self.calendar,
                     params={"days": {"type": "integer", "default": 7}}),
        ]


class DemoJellyfin(_DemoBase):
    name = "demo_jellyfin"

    async def health(self) -> dict:
        return {"ok": True, "version": "10.11.8 (demo)", "server": "demo-server"}

    async def now_playing(self) -> dict:
        return {"count": 1, "sessions": [
            {"user": "demo", "client": "Jellyfin Mobile", "item": "The Bear S03E03"},
        ]}

    async def search(self, query: str, limit: int = 10) -> dict:
        catalogue = [
            ("Interstellar", "Movie", 2014),
            ("The Bear", "Series", 2022),
            ("Severance", "Series", 2022),
            ("Foundation", "Series", 2021),
            ("Dune: Part Two", "Movie", 2024),
        ]
        q = query.lower()
        hits = [{"name": n, "type": t, "year": y} for n, t, y in catalogue if q in n.lower()]
        return {"count": len(hits), "items": hits[:limit]}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="jellyfin_now_playing", description="Who's watching what right now.",
                     handler=self.now_playing),
            ToolSpec(name="jellyfin_search", description="Search the Jellyfin demo library.",
                     handler=self.search,
                     params={"query": {"type": "string", "required": True},
                             "limit": {"type": "integer", "default": 10}}),
        ]


class DemoQBittorrent(_DemoBase):
    name = "demo_qbittorrent"

    async def health(self) -> dict:
        # Flip a coin per process for variety — the agent's auto-repair
        # gets to demo handling an unhealthy service occasionally.
        unhealthy = _RAND.random() < 0.15
        if unhealthy:
            return {"ok": False, "error": "demo: qBittorrent unreachable"}
        return {"ok": True, "version": "5.0.3 (demo)"}

    async def transfer_info(self) -> dict:
        return {"dl_rate": 1_572_864, "up_rate": 102_400, "connected_peers": 41}

    async def list_torrents(self, filter: str = "all") -> dict:
        torrents = [
            {"name": "The Bear S03 [1080p]", "state": "downloading", "progress": 0.62},
            {"name": "Severance S02 [1080p]", "state": "stalledDL", "progress": 0.04},
            {"name": "Dune Part Two [2160p]", "state": "uploading", "progress": 1.0},
        ]
        if filter != "all":
            torrents = [t for t in torrents if t["state"] == filter]
        return {"count": len(torrents), "torrents": torrents}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="qbittorrent_transfer_info", description="Demo download/upload rates.",
                     handler=self.transfer_info),
            ToolSpec(name="qbittorrent_list_torrents", description="List demo torrents.",
                     handler=self.list_torrents,
                     params={"filter": {"type": "string", "default": "all"}}),
        ]


class DemoOllama(_DemoBase):
    name = "demo_ollama"

    async def health(self) -> dict:
        return {"ok": True, "model_count": 3}

    async def list_models(self) -> dict:
        return {"models": [
            {"name": "qwen3.5:4b", "size_gb": 3.4},
            {"name": "llama3.1:8b", "size_gb": 4.7},
            {"name": "nomic-embed-text", "size_gb": 0.3},
        ]}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="ollama_list_models", description="Demo: list local Ollama models.",
                     handler=self.list_models),
        ]


class DemoPaperless(_DemoBase):
    name = "demo_paperless"

    async def health(self) -> dict:
        return {"ok": True, "endpoints": 14}

    async def search(self, query: str, limit: int = 10) -> dict:
        docs = [
            {"id": 1, "title": "Lease agreement 2024", "tags": ["legal"]},
            {"id": 2, "title": "Internet bill - Comcast", "tags": ["bills"]},
            {"id": 3, "title": "Tax return 2023", "tags": ["taxes", "important"]},
            {"id": 4, "title": "Car insurance policy", "tags": ["car", "insurance"]},
        ]
        q = query.lower()
        hits = [d for d in docs if q in d["title"].lower() or any(q in t for t in d["tags"])]
        return {"count": len(hits), "items": hits[:limit]}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="paperless_search", description="Search the Paperless demo library.",
                     handler=self.search,
                     params={"query": {"type": "string", "required": True},
                             "limit": {"type": "integer", "default": 10}}),
        ]


DEMO_SERVICES = {
    "sonarr": DemoSonarr,
    "jellyfin": DemoJellyfin,
    "qbittorrent": DemoQBittorrent,
    "ollama": DemoOllama,
    "paperless": DemoPaperless,
}
