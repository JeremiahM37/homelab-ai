"""Statistical anomaly detector — hour-of-day baseline + z-score flagging.

Records numeric metrics from each service's `health()` output every scan.
After collecting enough samples, flags any value whose z-score (against the
mean/stddev of the same hour-of-day over the past N days) exceeds a
threshold.

This catches things Prometheus alert thresholds miss: "CPU at 70% is
normal at 11pm during media indexing, but at 4am that's unusual".

Opt-in: enable `features.anomalies.enabled`. The module also has to be
listed under `agent.modules`. (Anomaly detection is a normal scan module,
the feature flag just gates whether the SQLite history is written —
disabled-but-listed = zero cost.)
"""
from __future__ import annotations

import logging
import math
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .base import AgentModule, Finding, Severity

if TYPE_CHECKING:
    pass

logger = logging.getLogger("homelab_ai.agent.anomaly")


SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_history (
    service TEXT NOT NULL,
    metric  TEXT NOT NULL,
    ts      REAL NOT NULL,
    hour    INTEGER NOT NULL,        -- 0-23 for hour-of-day bucketing
    value   REAL NOT NULL,
    PRIMARY KEY (service, metric, ts)
);
CREATE INDEX IF NOT EXISTS idx_metric_hour
    ON metric_history(service, metric, hour, ts);
"""


def _extract_metrics(svc_name: str, health: dict) -> list[tuple[str, float]]:
    """Pull every numeric value out of a service's health() response.

    Skips obvious bools (treats True as 1.0, False as 0.0 only at top level —
    `ok` is interesting; but we ignore nested True/False because they're
    flags, not metrics).
    """
    out: list[tuple[str, float]] = []
    for k, v in (health or {}).items():
        if isinstance(v, bool):
            out.append((k, 1.0 if v else 0.0))
        elif isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v):
            out.append((k, float(v)))
    return out


class AnomalyDetectorModule(AgentModule):
    name = "anomaly_detector"

    def __init__(self, cfg, services):
        super().__init__(cfg, services)
        # Read the feature config inline so we don't have to plumb Features
        # through to every module.
        raw = (cfg._raw.get("features") or {}).get("anomalies") or {}
        if not raw.get("enabled"):
            self._enabled = False
            return
        self._enabled = True
        self._db_path = Path(raw.get("db_path", "./data/anomalies.db"))
        self._stddev_threshold = float(raw.get("stddev_threshold", 3.0))
        self._min_samples = int(raw.get("min_samples", 12))
        self._history_days = int(raw.get("history_days", 7))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def _record(self, service: str, metric: str, value: float) -> None:
        """Store one numeric metric sample with its hour-of-day."""
        now = time.time()
        hour = datetime.fromtimestamp(now).hour
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO metric_history VALUES (?, ?, ?, ?, ?)",
                (service, metric, now, hour, value),
            )
            cutoff = now - self._history_days * 86400
            self._conn.execute(
                "DELETE FROM metric_history WHERE service = ? AND metric = ? AND ts < ?",
                (service, metric, cutoff),
            )

    def _baseline(self, service: str, metric: str, hour: int) -> tuple[float, float, int]:
        """Mean/stddev of this metric at this hour-of-day over the retention window."""
        rows = self._conn.execute(
            "SELECT value FROM metric_history WHERE service = ? AND metric = ? AND hour = ?",
            (service, metric, hour),
        ).fetchall()
        n = len(rows)
        if n < 2:
            return 0.0, 0.0, n
        values = [r[0] for r in rows]
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
        return mean, math.sqrt(var), n

    async def scan(self) -> list[Finding]:
        """Record metrics from service health and flag hour-of-day z-score outliers."""
        if not self._enabled:
            return []
        findings: list[Finding] = []
        for name, svc in self.services.items():
            try:
                health = await svc.health()
            except Exception:
                continue
            if not isinstance(health, dict):
                continue
            hour = datetime.now().hour
            for metric, value in _extract_metrics(name, health):
                mean, stddev, n = self._baseline(name, metric, hour)
                self._record(name, metric, value)
                if n < self._min_samples:
                    continue
                # Two cases:
                #   stddev > 0: standard z-score formula.
                #   stddev == 0 (perfectly constant baseline): any deviation
                #   from mean is anomalous by definition. We tolerate tiny
                #   float noise (~1e-9) so an integer counter that's been
                #   exactly 0 every scan doesn't false-alarm on float jitter.
                if stddev > 0:
                    z = (value - mean) / stddev
                    anomalous = abs(z) >= self._stddev_threshold
                else:
                    if abs(value - mean) < 1e-9:
                        continue
                    z = math.inf if value > mean else -math.inf
                    anomalous = True
                if anomalous:
                    direction = "high" if z > 0 else "low"
                    findings.append(Finding(
                        module=self.name,
                        target=f"{name}.{metric}",
                        severity=Severity.WARNING,
                        message=(
                            f"{name}.{metric} is unusually {direction}: "
                            f"value={value:.3g}, mean={mean:.3g}, "
                            f"stddev={stddev:.3g}, z={z:+.2f}"
                        ),
                        context={
                            "service": name, "metric": metric, "value": value,
                            "mean": mean, "stddev": stddev, "z_score": z,
                            "samples": n,
                        },
                    ))
        return findings
