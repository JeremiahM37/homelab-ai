"""Outbound notifier — Discord + generic webhook, with dedup + rate limiting.

State is in-memory by default (resets on restart). For long-running deployments,
pass `state_path` to persist dedup state to a JSON file.
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from homelab_ai.agent.modules.base import Finding
    from homelab_ai.config import NotifyConfig

logger = logging.getLogger("homelab_ai.notifications")


_SEV_COLOR = {
    "INFO": 0x3B82F6,      # blue
    "WARNING": 0xEAB308,   # yellow
    "ERROR": 0xEF4444,     # red
    "CRITICAL": 0x991B1B,  # dark red
}


class Notifier:
    def __init__(
        self,
        config: NotifyConfig,
        http: aiohttp.ClientSession,
        state_path: str | Path | None = None,
    ):
        self.config = config
        self.http = http
        self.state_path = Path(state_path) if state_path else None
        # Per-fingerprint last-sent timestamp.
        self._sent: dict[str, float] = {}
        # Sliding-window timestamps of all sends — for the per-hour cap.
        self._recent: deque[float] = deque(maxlen=200)
        self._load_state()

    # ── public ───────────────────────────────────────────────────────────

    async def publish(self, finding: Finding, action_taken: str | None = None) -> bool:
        """Send the alert if not in cooldown and under the hourly cap.

        Returns True if the alert was sent, False if suppressed.
        """
        fp = self._fp(finding)
        now = time.time()

        # Dedup: same fingerprint within 1 hour → suppress.
        if (last := self._sent.get(fp)) and (now - last < 3600):
            return False

        # Hourly cap.
        while self._recent and now - self._recent[0] > 3600:
            self._recent.popleft()
        if len(self._recent) >= self.config.rate_limit_per_hour:
            logger.info("notification rate-limit hit (%d/hr) — suppressing %s",
                        self.config.rate_limit_per_hour, finding.target)
            return False

        sent = False
        if self.config.discord_webhook:
            sent = await self._send_discord(finding, action_taken) or sent
        if self.config.generic_webhook:
            sent = await self._send_generic(finding, action_taken) or sent

        if sent:
            self._sent[fp] = now
            self._recent.append(now)
            self._save_state()
        return sent

    async def publish_resolved(self, finding: Finding) -> bool:
        """Optional resolved notice — short, lower-priority, doesn't count against rate cap."""
        fp = self._fp(finding)
        if fp not in self._sent:
            return False  # never sent a "broken" alert, nothing to resolve
        del self._sent[fp]
        self._save_state()
        msg = f"✓ resolved: `{finding.target}` — {finding.message[:200]}"
        if self.config.discord_webhook:
            try:
                async with self.http.post(self.config.discord_webhook, json={"content": msg}) as r:
                    return r.status < 300
            except Exception as e:
                logger.warning("discord resolve send failed: %s", e)
        return False

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _fp(finding: Finding) -> str:
        return f"{finding.module}|{finding.target}|{finding.message[:200]}"

    async def _send_discord(self, finding: Finding, action: str | None) -> bool:
        color = _SEV_COLOR.get(finding.severity.name, 0x6B7280)
        embed = {
            "title": f"[{finding.severity.name}] {finding.target}",
            "description": finding.message[:1500],
            "color": color,
            "fields": [],
            "footer": {"text": f"module: {finding.module}"},
        }
        if finding.fix_hint:
            embed["fields"].append({"name": "fix hint", "value": f"`{finding.fix_hint}`", "inline": True})
        if action:
            embed["fields"].append({"name": "action taken", "value": action, "inline": True})
        try:
            async with self.http.post(self.config.discord_webhook, json={"embeds": [embed]}) as r:
                if r.status >= 300:
                    body = (await r.text())[:200]
                    logger.warning("discord %s: %s", r.status, body)
                    return False
                return True
        except Exception as e:
            logger.warning("discord send failed: %s", e)
            return False

    async def _send_generic(self, finding: Finding, action: str | None) -> bool:
        payload = {
            "severity": finding.severity.name,
            "module": finding.module,
            "target": finding.target,
            "message": finding.message,
            "fix_hint": finding.fix_hint,
            "context": finding.context,
            "action_taken": action,
            "timestamp": time.time(),
        }
        try:
            async with self.http.post(self.config.generic_webhook, json=payload) as r:
                return r.status < 300
        except Exception as e:
            logger.warning("generic webhook failed: %s", e)
            return False

    # ── state persistence ────────────────────────────────────────────────

    def _load_state(self) -> None:
        if not self.state_path or not self.state_path.is_file():
            return
        try:
            data = json.loads(self.state_path.read_text())
            self._sent = data.get("sent", {})
            for ts in data.get("recent", [])[-200:]:
                self._recent.append(float(ts))
        except Exception as e:
            logger.warning("notifier state load failed: %s", e)

    def _save_state(self) -> None:
        if not self.state_path:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({
                "sent": self._sent,
                "recent": list(self._recent),
            }))
        except Exception as e:
            logger.warning("notifier state save failed: %s", e)
