"""Load service plugins by name.

Lookup order:
  1. Built-in plugin (homelab_ai/services/<name>.py)
  2. User plugin dir (~/.config/homelab-ai/services/<name>.py)
  3. Env var HOMELAB_AI_PLUGINS=/path/to/dir
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

from .base import Service

if TYPE_CHECKING:
    from homelab_ai.config import Config

logger = logging.getLogger("homelab_ai.services")


def _user_plugin_dirs() -> list[Path]:
    dirs = [Path.home() / ".config" / "homelab-ai" / "services"]
    if extra := os.environ.get("HOMELAB_AI_PLUGINS"):
        dirs.append(Path(extra))
    return [d for d in dirs if d.is_dir()]


def _load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"homelab_ai_user.{name}", path)
    if not spec or not spec.loader:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_service_class(module, want_name: str | None = None) -> type[Service] | None:
    """Pick a Service subclass exposed by the module.

    If `want_name` is given, prefer a class whose `.name` attribute matches
    (this lets `sonarr.py` re-export `Sonarr` from `arr.py` cleanly). Otherwise
    return the first Service subclass found.
    """
    candidates = []
    for _name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and issubclass(obj, Service) and obj is not Service:
            candidates.append(obj)
    if want_name:
        for c in candidates:
            if getattr(c, "name", None) == want_name:
                return c
    return candidates[0] if candidates else None


def _resolve_plugin(name: str) -> type[Service] | None:
    # Built-in
    try:
        module = importlib.import_module(f"homelab_ai.services.{name}")
        if cls := _find_service_class(module, want_name=name):
            return cls
    except ImportError:
        pass
    # User
    for d in _user_plugin_dirs():
        path = d / f"{name}.py"
        if path.is_file():
            try:
                module = _load_module_from_path(name, path)
                if cls := _find_service_class(module, want_name=name):
                    return cls
            except Exception as e:
                logger.warning("failed to load user plugin %s: %s", path, e)
    return None


def load_services(cfg: Config, http: aiohttp.ClientSession) -> dict[str, Service]:
    """Instantiate every service named in cfg.services and return {name: instance}."""
    out: dict[str, Service] = {}
    for name, settings in cfg.services.items():
        if not isinstance(settings, dict):
            logger.warning("services.%s: expected a dict, got %r — skipping", name, type(settings))
            continue
        cls = _resolve_plugin(name)
        if not cls:
            logger.warning("no plugin found for service %r — skipping", name)
            continue
        try:
            out[name] = cls(settings, http)
        except Exception as e:
            logger.exception("failed to instantiate service %s: %s", name, e)
    return out
