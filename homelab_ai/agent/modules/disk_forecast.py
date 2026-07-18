"""Disk usage trend forecaster.

Records (timestamp, percent) on every scan and projects ahead. Warns when
the projected days-to-full crosses a threshold.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .base import AgentModule, Finding, Severity

if TYPE_CHECKING:
    pass


_DB_FILE = "data/disk_history.db"


class DiskForecastModule(AgentModule):
    name = "disk_forecast"

    DEFAULT_PATHS = ["/"]
    WARN_DAYS = 30   # warn if projected to fill in <30 days
    CRIT_DAYS = 7

    def __init__(self, cfg, services):
        super().__init__(cfg, services)
        self._db_path = Path(_DB_FILE)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS disk_history (
                path TEXT NOT NULL,
                ts REAL NOT NULL,
                used_bytes INTEGER NOT NULL,
                total_bytes INTEGER NOT NULL,
                PRIMARY KEY (path, ts)
            )
        """)
        self._conn.commit()

    def _record(self, path: str, used: int, total: int) -> None:
        """Append a (timestamp, used-bytes) sample for this path."""
        now = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO disk_history VALUES (?, ?, ?, ?)",
                (path, now, used, total),
            )
            # Trim history older than 30 days.
            self._conn.execute(
                "DELETE FROM disk_history WHERE path = ? AND ts < ?",
                (path, now - 30 * 86400),
            )

    def _history(self, path: str) -> list[tuple[float, int]]:
        """All recorded (timestamp, used-bytes) samples for a path, oldest first."""
        rows = self._conn.execute(
            "SELECT ts, used_bytes FROM disk_history WHERE path = ? ORDER BY ts ASC", (path,)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def _days_to_full(self, path: str, total: int) -> float | None:
        """Linear-regression projection of days until the path reaches capacity."""
        hist = self._history(path)
        # Need enough samples spanning at least a few hours.
        if len(hist) < 5 or hist[-1][0] - hist[0][0] < 6 * 3600:
            return None
        # Linear regression on (t, used).
        n = len(hist)
        mean_t = sum(t for t, _ in hist) / n
        mean_u = sum(u for _, u in hist) / n
        num = sum((t - mean_t) * (u - mean_u) for t, u in hist)
        den = sum((t - mean_t) ** 2 for t, _ in hist)
        if den == 0:
            return None
        slope = num / den  # bytes per second
        if slope <= 0:
            return None
        latest_used = hist[-1][1]
        days = (total - latest_used) / slope / 86400
        return max(0.0, days)

    async def scan(self) -> list[Finding]:
        """Record current disk usage and warn when the projected days-to-full is low."""
        agent_cfg = (self.cfg._raw.get("agent") or {}).get("disk_forecast") or {}
        paths = agent_cfg.get("paths") or self.DEFAULT_PATHS
        warn_days = agent_cfg.get("warn_days", self.WARN_DAYS)
        crit_days = agent_cfg.get("crit_days", self.CRIT_DAYS)

        findings: list[Finding] = []
        for p in paths:
            try:
                u = shutil.disk_usage(p)
            except FileNotFoundError:
                continue
            self._record(p, u.used, u.total)
            days = self._days_to_full(p, u.total)
            if days is None:
                continue
            if days <= crit_days:
                findings.append(Finding(
                    module=self.name,
                    target=p,
                    severity=Severity.CRITICAL,
                    message=f"{p} projected full in {days:.1f} days",
                    context={"days_to_full": round(days, 1), "path": p},
                ))
            elif days <= warn_days:
                findings.append(Finding(
                    module=self.name,
                    target=p,
                    severity=Severity.WARNING,
                    message=f"{p} projected full in {days:.1f} days",
                    context={"days_to_full": round(days, 1), "path": p},
                ))
        return findings
