"""Base class every agent module inherits from."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homelab_ai.config import Config
    from homelab_ai.services.base import Service


class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


@dataclass
class Finding:
    """One result from a module scan — something interesting the agent noticed.

    `fix_hint` is a string the rule-based Tier-1 can match against (e.g.
    "restart_container", "retry_indexer"). Modules don't *call* fixes
    directly — they just describe what's wrong; the fixer decides.
    """
    module: str
    target: str
    severity: Severity
    message: str
    fix_hint: str = ""
    context: dict = field(default_factory=dict)

    def fingerprint(self) -> str:
        return f"{self.module}|{self.target}|{self.message[:200]}"


class AgentModule:
    """Override in subclasses. Set `name` and implement `scan()`."""
    name: str = "base"

    def __init__(self, cfg: "Config", services: dict[str, "Service"]):
        self.cfg = cfg
        self.services = services

    async def scan(self) -> list[Finding]:
        raise NotImplementedError
