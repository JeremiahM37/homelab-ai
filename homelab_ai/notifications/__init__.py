"""Outbound alerts — Discord webhook + generic webhook.

Provides:
- Dedup by fingerprint so a flapping service doesn't pager-bomb you.
- Rate-limit cap per hour (default 20).
- Resolved notices when an open failure clears.
- Severity-aware formatting.

Plugins call `Notifier.publish(finding)`; everything else is internal.
"""
from .notifier import Notifier

__all__ = ["Notifier"]
