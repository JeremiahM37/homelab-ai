"""Append-only audit log for AI-driven changes.

Every action the Tier-3 fixer takes is logged in markdown so a human can
review it after the fact. Format is intentionally human-readable; the file
is meant to be `tail -f`-able and `grep`-able, not parsed by a tool.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("homelab_ai.fixer.audit")


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                "# Homelab-AI Audit Log\n\n"
                "Every AI-driven change is recorded here. Review periodically; "
                "use `revert` script if anything looks wrong.\n\n"
            )

    def record(
        self,
        action: str,
        target: str,
        rationale: str,
        diff: str | None = None,
        backup_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.path.open("a") as f:
            f.write(f"## {ts}  ·  {action}  ·  `{target}`\n\n")
            f.write(f"**Rationale:** {rationale}\n\n")
            if backup_id:
                f.write(f"**Backup:** `{backup_id}`\n\n")
            if extra:
                for k, v in extra.items():
                    f.write(f"- **{k}:** {v}\n")
                f.write("\n")
            if diff:
                f.write("```diff\n")
                f.write(diff.strip() + "\n")
                f.write("```\n\n")
            f.write("---\n\n")
