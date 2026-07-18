"""Web config editor — GET schema, GET current, PUT save.

Opt-in feature (`features.config_editor.enabled`). When on, the PWA's
Config tab can read the schema, render forms, and save back to disk.

Security: changes hit disk *only* if the request is authenticated. The
auth middleware is already in front of this router; we additionally
refuse to write if `auth.enabled` is off, on the theory that an unauth'd
config editor is a footgun.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Body, HTTPException, Request

logger = logging.getLogger("homelab_ai.api.config_editor")
router = APIRouter(prefix="/api/config", tags=["config"])


def _path(request: Request) -> Path:
    features = request.app.state.cfg._features
    return Path(features.config_editor.config_path)


@router.get("/schema")
async def schema() -> dict:
    """Return a minimal schema describing top-level config sections so the
    PWA can render fields. Each section: {description, fields[]}.

    Intentionally not a full JSON-Schema — homelab-ai config has a few
    irregular spots (services is an open dict). The PWA renders the
    well-known sections as forms and falls back to a YAML textarea for
    the rest.
    """
    return {
        "sections": [
            {
                "name": "server",
                "description": "HTTP server",
                "fields": [
                    {"name": "host", "type": "string"},
                    {"name": "port", "type": "integer", "min": 1, "max": 65535},
                ],
            },
            {
                "name": "llm",
                "description": "LLM backend",
                "fields": [
                    {"name": "backend", "type": "enum",
                     "options": ["auto", "ollama", "openai_compat"]},
                    {"name": "url", "type": "string"},
                    {"name": "api_key", "type": "secret"},
                    {"name": "small_model", "type": "string"},
                    {"name": "smart_model", "type": "string"},
                    {"name": "embed_model", "type": "string"},
                ],
            },
            {
                "name": "auth",
                "description": "Authentication",
                "fields": [
                    {"name": "enabled", "type": "bool"},
                    {"name": "api_key", "type": "secret"},
                ],
            },
            {
                "name": "agent",
                "description": "Agent / auto-repair",
                "fields": [
                    {"name": "enabled", "type": "bool"},
                    {"name": "scan_interval", "type": "integer", "min": 30},
                ],
            },
            {
                "name": "features",
                "description": "Optional features (each has its own block)",
                "fields": [
                    {"name": "metrics.enabled", "type": "bool"},
                    {"name": "ntfy.enabled", "type": "bool"},
                    {"name": "gotify.enabled", "type": "bool"},
                    {"name": "email.enabled", "type": "bool"},
                    {"name": "scheduler.enabled", "type": "bool"},
                    {"name": "webhooks.enabled", "type": "bool"},
                    {"name": "multi_llm.enabled", "type": "bool"},
                    {"name": "history.enabled", "type": "bool"},
                    {"name": "rag.enabled", "type": "bool"},
                    {"name": "mcp_http.enabled", "type": "bool"},
                    {"name": "automations.enabled", "type": "bool"},
                    {"name": "anomalies.enabled", "type": "bool"},
                    {"name": "config_editor.enabled", "type": "bool"},
                ],
            },
        ],
    }


@router.get("/current")
async def current(request: Request) -> dict:
    """Return the raw YAML text + parsed object. Secrets are redacted."""
    path = _path(request)
    if not path.is_file():
        return {"path": str(path), "yaml": "", "parsed": {}}
    text = path.read_text()
    parsed = yaml.safe_load(text) or {}
    redacted = _redact_secrets(parsed)
    return {
        "path": str(path),
        "yaml": text,
        "parsed": redacted,
    }


@router.put("/save")
async def save(request: Request, body: dict = Body(...)) -> dict:
    """Save config.yaml. Two modes:
       - {"yaml": "..."}  — raw text mode (validated as YAML before write)
       - {"parsed": {...}} — typed mode; merged with on-disk current
    """
    if not request.app.state.cfg.auth.enabled:
        raise HTTPException(403, "Refusing to write config while auth is disabled. "
                                  "Turn on auth.enabled first.")
    path = _path(request)
    if "yaml" in body:
        text = body["yaml"]
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise HTTPException(400, f"invalid YAML: {e}") from e
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    elif "parsed" in body:
        merged = body["parsed"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(merged, sort_keys=False))
    else:
        raise HTTPException(400, "expected 'yaml' or 'parsed' in body")
    return {"ok": True, "restart_required": True,
            "message": "Restart the server to apply changes."}


_SECRET_KEYS = {"api_key", "password", "token", "smtp_password", "smart_api_key"}


def _redact_secrets(obj):
    """Recursively mask secret-looking values before returning config to the UI."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in _SECRET_KEYS and isinstance(v, str) and v:
                out[k] = "•" * 8 + " (set)"
            else:
                out[k] = _redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [_redact_secrets(x) for x in obj]
    return obj
