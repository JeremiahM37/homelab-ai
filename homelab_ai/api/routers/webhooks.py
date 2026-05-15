"""Inbound webhook receiver — opt-in feature.

Configured as:

  features:
    webhooks:
      enabled: true
      receivers:
        grafana_alert:
          secret: "${WEBHOOK_GRAFANA_SECRET}"
          tool: restart_service          # tool to invoke when this hook fires
          args: {service: "{{service}}"}  # values from POST body merged in
        sonarr_grab:
          secret: ""                      # no secret = open
          tool: sonarr_queue_summary

`POST /api/webhooks/{name}` with the secret as `?secret=...` or
`X-Webhook-Secret` header fires the matching tool.

Off by default — the router is only added to the app if
`features.webhooks.enabled` is true.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

logger = logging.getLogger("homelab_ai.api.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _check_secret(request: Request, expected: str) -> bool:
    if not expected:
        return True   # no secret configured = open
    provided = (
        request.headers.get("x-webhook-secret")
        or request.query_params.get("secret")
    )
    if not provided:
        return False
    import hmac
    return hmac.compare_digest(provided.encode(), expected.encode())


def _render_args(template: dict, body: dict) -> dict:
    """Substitute {{key}} placeholders in arg values with values from the body."""
    out: dict[str, Any] = {}
    for k, v in (template or {}).items():
        if isinstance(v, str) and "{{" in v and "}}" in v:
            try:
                key = v.split("{{", 1)[1].split("}}")[0].strip()
                out[k] = body.get(key, v)
            except IndexError:
                out[k] = v
        else:
            out[k] = v
    return out


@router.post("/{name}")
async def receive(name: str, request: Request, body: dict = Body(default={})) -> dict:
    features = request.app.state.cfg._features  # set on startup if webhooks enabled
    receiver = (features.webhooks.receivers or {}).get(name)
    if not receiver:
        raise HTTPException(404, f"no webhook receiver named {name!r}")
    if not _check_secret(request, receiver.get("secret", "")):
        raise HTTPException(401, "invalid webhook secret")

    tool_name = receiver.get("tool")
    args = _render_args(receiver.get("args") or {}, body or {})

    services = request.app.state.services
    handler = None
    for svc in services.values():
        for spec in svc.tools():
            if spec.name == tool_name:
                handler = spec.handler
                break
        if handler:
            break
    if not handler:
        raise HTTPException(500, f"webhook {name!r} references unknown tool {tool_name!r}")

    try:
        result = await handler(**args)
    except Exception as e:
        logger.warning("webhook %s tool %s failed: %s", name, tool_name, e)
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True, "tool": tool_name, "result": result}
