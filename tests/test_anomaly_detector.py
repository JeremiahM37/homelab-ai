"""Anomaly detector — baseline math + threshold behaviour."""
import asyncio

import pytest

from homelab_ai.agent.modules.anomaly_detector import (
    AnomalyDetectorModule,
    _extract_metrics,
)
from homelab_ai.config import Config


def test_extract_metrics_pulls_numeric_keys():
    out = _extract_metrics("svc", {
        "ok": True,
        "version": "4.0.0",   # string, ignored
        "queue_size": 42,
        "load": 0.75,
        "broken": float("nan"),  # NaN, ignored
    })
    names = {k for k, _ in out}
    assert "ok" in names         # bool → float
    assert "queue_size" in names
    assert "load" in names
    assert "version" not in names
    assert "broken" not in names


def _make_module(tmp_path, services=None, enabled=True):
    cfg = Config()
    cfg._raw = {"features": {"anomalies": {
        "enabled": enabled,
        "db_path": str(tmp_path / "anom.db"),
        "stddev_threshold": 2.0,
        "min_samples": 3,
        "history_days": 7,
    }}}
    return AnomalyDetectorModule(cfg, services or {})


def test_module_disabled_returns_empty(tmp_path):
    mod = _make_module(tmp_path, enabled=False)
    # Disabled module doesn't open the DB.
    result = asyncio.run(mod.scan())
    assert result == []


@pytest.mark.asyncio
async def test_module_builds_baseline_then_flags_outlier(tmp_path):
    """Feed normal values for a while, then a wildly-off value — should flag."""
    healths = [{"load": 0.5}] * 10 + [{"load": 10.0}]
    idx = {"i": 0}

    class _Svc:
        async def health(self):
            v = healths[min(idx["i"], len(healths) - 1)]
            idx["i"] += 1
            return v
        def tools(self): return []

    mod = _make_module(tmp_path, services={"x": _Svc()})
    # Run through enough samples to build the hour-of-day baseline.
    for _ in range(10):
        await mod.scan()
    out = await mod.scan()
    # Now load=10.0 should flag.
    anomalies = [f for f in out if f.target == "x.load"]
    assert anomalies, "expected an anomaly for the spike"
    assert anomalies[0].context["z_score"] > 2


@pytest.mark.asyncio
async def test_module_quiet_when_under_min_samples(tmp_path):
    class _Svc:
        async def health(self): return {"load": 5.0}
        def tools(self): return []

    mod = _make_module(tmp_path, services={"x": _Svc()})
    out = await mod.scan()
    # First scan: 0 samples in history — no anomaly possible.
    assert out == []
