"""Probe well-known ports for installed services.

The probe is intentionally narrow: a 1-2 second HTTP HEAD/GET, looking for
a signature string in the response body or headers. We don't want to lock
up boot if a port is firewalled.

Each entry in KNOWN_SERVICES is:
    {"plugin": "sonarr", "port": 8989, "path": "/", "signature": "Sonarr"}

If the probe succeeds, the discovery output includes the plugin name + a
suggested config block. The caller (typically `homelab-ai init`) decides
which ones to keep.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger("homelab_ai.discovery")


@dataclass(frozen=True)
class ServiceProbe:
    plugin: str
    port: int
    path: str = "/"
    signature: str = ""              # substring to look for in body
    header_signature: tuple[str, str] = ("", "")  # (header-name, substr)
    needs_api_key: bool = True
    notes: str = ""


KNOWN_SERVICES: list[ServiceProbe] = [
    # *arr family — all expose a recognizable login page or system info.
    ServiceProbe("sonarr", 8989, "/", "Sonarr"),
    ServiceProbe("radarr", 7878, "/", "Radarr"),
    ServiceProbe("lidarr", 8686, "/", "Lidarr"),
    ServiceProbe("readarr", 8787, "/", "Readarr"),
    ServiceProbe("prowlarr", 9696, "/", "Prowlarr"),
    ServiceProbe("bazarr", 6767, "/", "Bazarr"),

    # Media servers.
    ServiceProbe("jellyfin", 8096, "/System/Info/Public", "ProductName",
                 needs_api_key=False),
    ServiceProbe("jellyseerr", 5055, "/api/v1/status", "version"),

    # Photo / docs.
    ServiceProbe("immich", 2283, "/api/server/ping", "pong",
                 needs_api_key=False),
    ServiceProbe("paperless", 8000, "/api/", "documents"),

    # Books / comics.
    ServiceProbe("audiobookshelf", 13378, "/ping", "Ping",
                 needs_api_key=False),
    ServiceProbe("kavita", 5005, "/", "Kavita",
                 needs_api_key=False),

    # Cooking / inventory.
    ServiceProbe("mealie", 9925, "/api/app/about", "version",
                 needs_api_key=False),
    ServiceProbe("homebox", 7745, "/api/v1/status", "ok",
                 needs_api_key=False),

    # Search / monitoring.
    ServiceProbe("searxng", 8888, "/", "SearXNG",
                 needs_api_key=False),
    ServiceProbe("uptime_kuma", 3001, "/", "Uptime Kuma",
                 needs_api_key=False),

    # Downloaders.
    ServiceProbe("qbittorrent", 8080, "/api/v2/app/version", "",
                 needs_api_key=False,
                 notes="needs username + password in config"),
    ServiceProbe("transmission", 9091, "/transmission/rpc", "",
                 needs_api_key=False),
    ServiceProbe("sabnzbd", 8085, "/api?mode=version", "version"),

    # Smart home / DNS.
    ServiceProbe("home_assistant", 8123, "/", "Home Assistant",
                 needs_api_key=False, notes="needs long-lived access token"),
    ServiceProbe("adguard", 3000, "/control/status", "running",
                 needs_api_key=False, notes="needs basic auth"),

    # LLM backends.
    ServiceProbe("ollama", 11434, "/api/tags", "models",
                 needs_api_key=False),

    # Files.
    ServiceProbe("nextcloud", 80, "/status.php", "installed",
                 needs_api_key=False, notes="needs app password"),
]


async def probe_one(http: aiohttp.ClientSession, host: str, sp: ServiceProbe,
                    timeout: float = 1.5) -> dict | None:
    """Try one host+probe. Returns a config-block dict if found, else None."""
    url = f"http://{host}:{sp.port}{sp.path}"

    async def _do_probe():
        async with http.get(url, timeout=aiohttp.ClientTimeout(total=timeout),
                            allow_redirects=False) as r:
            return (await r.text())[:8000], dict(r.headers or {}), r.status
    try:
        # Belt-and-suspenders: enforce the timeout via wait_for too, so a
        # session whose connector ignores aiohttp.ClientTimeout (rare but
        # possible for non-default transports) still gets bounded.
        body, headers, status = await asyncio.wait_for(_do_probe(), timeout=timeout + 0.5)
    except TimeoutError:
        return None
    except Exception:
        return None

    has_signature = bool(sp.signature) or bool(sp.header_signature[0])
    matched = False
    if sp.signature and sp.signature.lower() in body.lower():
        matched = True
    elif sp.header_signature[0]:
        h, sub = sp.header_signature
        matched = sub.lower() in headers.get(h, "").lower()
    elif not has_signature and status < 500:
        # No signature configured at all — accept any 2xx or 401 (the latter
        # being "service is up, just needs auth").
        matched = status < 400 or status == 401

    if not matched:
        return None

    block: dict = {"url": f"http://{host}:{sp.port}"}
    if sp.needs_api_key:
        block["api_key"] = ""   # placeholder for user
    if sp.notes:
        block["_note"] = sp.notes
    return {
        "plugin": sp.plugin,
        "host": host,
        "port": sp.port,
        "config": block,
    }


async def discover(hosts: Iterable[str], timeout_per_probe: float = 1.5,
                   concurrency: int = 20) -> list[dict]:
    """Probe every (host, known_service) pair and return successful matches.

    Default `hosts` should include at least `127.0.0.1`. For Docker users,
    include `host.docker.internal` and your `<service-name>` if running in
    the same compose stack.
    """
    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession() as http:
        async def _bounded(host: str, sp: ServiceProbe):
            async with sem:
                return await probe_one(http, host, sp, timeout=timeout_per_probe)

        tasks = [
            _bounded(h, sp)
            for h in hosts
            for sp in KNOWN_SERVICES
        ]
        results = await asyncio.gather(*tasks)

    # Deduplicate by plugin — first hit wins.
    seen: set[str] = set()
    out: list[dict] = []
    for hit in results:
        if not hit or hit["plugin"] in seen:
            continue
        seen.add(hit["plugin"])
        out.append(hit)
    return out
