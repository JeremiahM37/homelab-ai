"""Prometheus /metrics endpoint — gated behind `features.metrics.enabled`.

Requires `pip install homelab-ai[metrics]`. The module imports
prometheus-client lazily so a non-metrics build has zero overhead.

Exposed metrics:
- homelab_ai_scans_total{result}            counter
- homelab_ai_fixes_total{tier,outcome}      counter
- homelab_ai_ai_calls_total{model,outcome}  counter
- homelab_ai_open_failures                  gauge
- homelab_ai_service_health{service}        gauge (1=ok, 0=down)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("homelab_ai.observability.metrics")

if TYPE_CHECKING:
    from fastapi import FastAPI

# Lazy import — `prometheus_client` is only loaded if the feature is on.
_initialized = False
_metrics: dict = {}


def _init():
    global _initialized, _metrics
    if _initialized:
        return
    from prometheus_client import Counter, Gauge
    _metrics["scans"] = Counter(
        "homelab_ai_scans_total", "Agent scans completed", ["result"],
    )
    _metrics["fixes"] = Counter(
        "homelab_ai_fixes_total", "Fixes attempted", ["tier", "outcome"],
    )
    _metrics["ai_calls"] = Counter(
        "homelab_ai_ai_calls_total", "AI agent calls", ["model", "outcome"],
    )
    _metrics["open_failures"] = Gauge(
        "homelab_ai_open_failures", "Open (unresolved) failures right now",
    )
    _metrics["service_health"] = Gauge(
        "homelab_ai_service_health",
        "1 = service healthy, 0 = unhealthy", ["service"],
    )
    _initialized = True


def record_scan(result: str) -> None:
    if _initialized:
        _metrics["scans"].labels(result=result).inc()


def record_fix(tier: int, outcome: str) -> None:
    if _initialized:
        _metrics["fixes"].labels(tier=str(tier), outcome=outcome).inc()


def record_ai_call(model: str, outcome: str) -> None:
    if _initialized:
        _metrics["ai_calls"].labels(model=model, outcome=outcome).inc()


def set_open_failures(n: int) -> None:
    if _initialized:
        _metrics["open_failures"].set(n)


def set_service_health(service: str, ok: bool) -> None:
    if _initialized:
        _metrics["service_health"].labels(service=service).set(1 if ok else 0)


def install(app: "FastAPI", path: str = "/metrics") -> None:
    """Wire the /metrics route into the FastAPI app. Idempotent."""
    try:
        _init()
    except ImportError:
        logger.error(
            "features.metrics is enabled but `prometheus-client` is not installed. "
            "Run: pip install homelab-ai[metrics]"
        )
        return

    from fastapi.responses import PlainTextResponse
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    @app.get(path, include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    logger.info("Prometheus /metrics endpoint registered at %s", path)
