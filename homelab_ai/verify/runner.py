"""Flow-test harness.

Tests are functions registered via `@check(group="core")`. Each one either
returns silently (pass), raises (fail), or returns a string (warning).

On failure the runner writes a `fix-request.md` the AI agent or the user
can pick up. Used as a nightly systemd timer in production.
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from homelab_ai.config import Config

logger = logging.getLogger("homelab_ai.verify")


@dataclass
class Check:
    name: str
    group: str
    fn: Callable


_CHECKS: list[Check] = []


def check(name: str | None = None, group: str = "core"):
    """Decorator: register a verification check."""
    def deco(fn):
        _CHECKS.append(Check(name=name or fn.__name__, group=group, fn=fn))
        return fn
    return deco


@dataclass
class Result:
    passed: int = 0
    failed: int = 0
    warned: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)
    duration_s: float = 0.0


def _run_checks(cfg: "Config") -> Result:
    # Importing pulls in @check-decorated functions.
    from . import builtin_checks  # noqa: F401
    selected = [c for c in _CHECKS if c.group in (cfg.verify.groups or [])]
    started = time.time()
    res = Result()
    for c in selected:
        try:
            out = c.fn(cfg)
            if isinstance(out, str) and out:
                res.warned += 1
                res.warnings.append((c.name, out))
                logger.warning("⚠ %s: %s", c.name, out)
            else:
                res.passed += 1
                logger.info("✓ %s", c.name)
        except Exception as e:
            res.failed += 1
            tb = traceback.format_exc(limit=3)
            res.failures.append((c.name, f"{type(e).__name__}: {e}\n{tb}"))
            logger.error("✗ %s: %s", c.name, e)
    res.duration_s = time.time() - started
    return res


def _write_fix_request(cfg: "Config", res: Result) -> Path | None:
    if not res.failures:
        return None
    path = Path(cfg.verify.fix_request_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["# Verify failures\n\n"]
    body.append(f"{res.failed} check(s) failed at {time.strftime('%Y-%m-%d %H:%M')}.\n\n")
    for name, err in res.failures:
        body.append(f"## {name}\n\n```\n{err.strip()}\n```\n\n")
    body.append("\nThe AI agent or operator should investigate the failures above.\n")
    body.append("Delete this file once all checks pass again.\n")
    path.write_text("".join(body))
    return path


def run_all(cfg: "Config") -> int:
    res = _run_checks(cfg)
    print(f"\nVERIFY: {res.passed} passed, {res.failed} failed, "
          f"{res.warned} warned ({res.duration_s:.1f}s)")
    if res.failures:
        path = _write_fix_request(cfg, res)
        if path:
            print(f"  fix-request: {path}")
    elif Path(cfg.verify.fix_request_path).exists():
        Path(cfg.verify.fix_request_path).unlink()
    return 0 if res.failed == 0 else 1
