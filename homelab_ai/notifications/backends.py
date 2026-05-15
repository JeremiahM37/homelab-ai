"""Additional notifier backends — email (SMTP), ntfy, gotify.

Each backend is a coroutine that takes (Finding, action_taken, http_session,
config) and returns True on success. The `Notifier` class dispatches based
on which features are enabled.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from homelab_ai.agent.modules.base import Finding
    from homelab_ai.features import EmailFeature, GotifyFeature, NtfyFeature

logger = logging.getLogger("homelab_ai.notifications.backends")


async def send_email(finding: "Finding", action: str | None, cfg: "EmailFeature") -> bool:
    """Run blocking SMTP in a thread so we don't stall the event loop."""
    if not cfg.smtp_host or not cfg.to_addresses:
        return False
    msg = EmailMessage()
    msg["From"] = cfg.from_address or cfg.smtp_user
    msg["To"] = ", ".join(cfg.to_addresses)
    msg["Subject"] = f"[homelab-ai] {finding.severity.name} — {finding.target}"
    body = f"""\
Module:   {finding.module}
Target:   {finding.target}
Severity: {finding.severity.name}
Message:  {finding.message}

Fix hint: {finding.fix_hint or '(none)'}
Action:   {action or '(none)'}
"""
    msg.set_content(body)
    try:
        await asyncio.to_thread(_send_email_sync, cfg, msg)
        return True
    except Exception as e:
        logger.warning("email send failed: %s", e)
        return False


def _send_email_sync(cfg: "EmailFeature", msg: EmailMessage) -> None:
    if cfg.use_tls:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as s:
            s.starttls(context=ctx)
            if cfg.smtp_user:
                s.login(cfg.smtp_user, cfg.smtp_password)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=10) as s:
            if cfg.smtp_user:
                s.login(cfg.smtp_user, cfg.smtp_password)
            s.send_message(msg)


async def send_ntfy(finding: "Finding", action: str | None, cfg: "NtfyFeature",
                    http: aiohttp.ClientSession) -> bool:
    if not cfg.url:
        return False
    headers = {
        "Title": f"[{finding.severity.name}] {finding.target}",
        "Priority": cfg.priority,
        "Tags": f"homelab-ai,{finding.module}",
    }
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"
    body = finding.message
    if action:
        body += f"\n\nAction: {action}"
    try:
        async with http.post(cfg.url, data=body.encode("utf-8"), headers=headers) as r:
            return r.status < 300
    except Exception as e:
        logger.warning("ntfy send failed: %s", e)
        return False


async def send_gotify(finding: "Finding", action: str | None, cfg: "GotifyFeature",
                      http: aiohttp.ClientSession) -> bool:
    if not cfg.url or not cfg.token:
        return False
    url = cfg.url.rstrip("/") + f"/message?token={cfg.token}"
    payload = {
        "title": f"[{finding.severity.name}] {finding.target}",
        "message": finding.message + (f"\n\nAction: {action}" if action else ""),
        "priority": {"INFO": 2, "WARNING": 5, "ERROR": 8, "CRITICAL": 10}.get(
            finding.severity.name, 5
        ),
    }
    try:
        async with http.post(url, json=payload) as r:
            return r.status < 300
    except Exception as e:
        logger.warning("gotify send failed: %s", e)
        return False
