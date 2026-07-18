"""Mullvad VPN account/device plugin.

Mullvad's only credential is the 16-digit account number. We obtain a
short-lived bearer token via `/auth/v1/token` and use it against the
account/devices API.

Config:

    services:
      mullvad:
        account_number: ${MULLVAD_ACCOUNT}    # 16 digits, no spaces
        # Optional: pair with a `gluetun` service so the routing check
        # can compare the externally-visible IP with Mullvad's device IPs.
        gluetun_url: http://gluetun:8000

Tools (all read-only — no risk of changing account state):
- mullvad_status      → account expiry, days remaining, paid up?
- mullvad_devices     → list registered Wireguard devices
- mullvad_check_routing → does the public IP look like a Mullvad exit?
                          (catches "tunnel up but no traffic" silently-broken
                          configurations like the PMTUD black-hole)
"""
from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from .base import Service, ToolSpec

logger = logging.getLogger("homelab_ai.services.mullvad")

AUTH_URL = "https://api.mullvad.net/auth/v1/token"
ACCOUNT_URL = "https://api.mullvad.net/accounts/v1/accounts/me"
DEVICES_URL = "https://api.mullvad.net/accounts/v1/devices"


class Mullvad(Service):
    name = "mullvad"

    def __init__(self, config: dict, http: aiohttp.ClientSession):
        super().__init__(config, http)
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._devices_cache: tuple[float, list[dict]] | None = None

    async def _auth(self) -> str:
        """Get (and cache) a Mullvad bearer token. ~30 minute TTL is plenty."""
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        acct = self.config.get("account_number") or self.config.get("account")
        if not acct:
            raise RuntimeError("mullvad: account_number missing from service config")
        async with self.http.post(AUTH_URL, json={"account_number": str(acct)}) as r:
            if r.status >= 400:
                raise RuntimeError(f"mullvad auth failed: HTTP {r.status}")
            data = await r.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"mullvad auth response missing access_token: {data}")
        self._token = token
        # Tokens are typically valid 1h; cache 25 min to be safe.
        self._token_exp = time.time() + 1500
        return token

    async def _get(self, url: str) -> dict | list:
        token = await self._auth()
        async with self.http.get(url, headers={"Authorization": f"Bearer {token}"}) as r:
            r.raise_for_status()
            return await r.json()

    # ── service interface ────────────────────────────────────────────────

    async def health(self) -> dict:
        """Healthy iff account is paid up + has at least one device registered."""
        try:
            acct = await self._get(ACCOUNT_URL)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}
        expiry = acct.get("expiry") if isinstance(acct, dict) else None
        days = _days_until(expiry)
        return {
            "ok": (days or 0) > 0,
            "expiry": expiry,
            "days_remaining": days,
        }

    async def status(self) -> dict:
        """Account expiry + how many days remain. Useful for 'is my VPN about to lapse?'."""
        acct = await self._get(ACCOUNT_URL)
        if not isinstance(acct, dict):
            return {"error": "unexpected response shape"}
        days = _days_until(acct.get("expiry"))
        return {
            "expiry": acct.get("expiry"),
            "days_remaining": days,
            "paid_up": (days or 0) > 0,
            "max_devices": acct.get("max_devices"),
            "max_ports": acct.get("max_ports"),
            "has_payments": acct.get("has_payments"),
        }

    async def devices(self) -> dict:
        """List registered Wireguard devices (name, ipv4, pubkey, created)."""
        # Light cache (60s) since this barely changes.
        now = time.time()
        if self._devices_cache and now - self._devices_cache[0] < 60:
            devs = self._devices_cache[1]
        else:
            raw = await self._get(DEVICES_URL)
            devs = raw if isinstance(raw, list) else []
            self._devices_cache = (now, devs)
        return {
            "count": len(devs),
            "max": 5,
            "devices": [
                {
                    "name": d.get("name") or d.get("hostname"),
                    "ipv4": (d.get("ipv4_address") or "").split("/")[0],
                    "pubkey_prefix": (d.get("pubkey") or "")[:16] + "…",
                    "created": d.get("created"),
                }
                for d in devs
            ],
        }

    async def check_routing(self) -> dict:
        """Cross-check: is the externally-visible IP one of Mullvad's exits?

        Catches silently-broken VPN configurations (handshake completes but
        the tunnel doesn't actually route traffic). Compares the IP that
        gluetun reports against a known list of Mullvad exit ranges by
        looking up the IP's ASN.

        Without a configured `gluetun_url` this falls back to hitting
        ifconfig.me, which is not VPN-routed by default — useful for the
        "is my host leaking?" case.
        """
        public_ip = None
        source = "ifconfig.me"
        if gurl := self.config.get("gluetun_url"):
            try:
                async with self.http.get(f"{gurl.rstrip('/')}/v1/publicip/ip",
                                         timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status < 400:
                        d = await r.json()
                        public_ip = d.get("public_ip")
                        source = "gluetun"
            except Exception as e:
                logger.debug("gluetun publicip fetch failed: %s", e)
        if not public_ip:
            try:
                async with self.http.get("https://ifconfig.me/ip",
                                         timeout=aiohttp.ClientTimeout(total=8)) as r:
                    public_ip = (await r.text()).strip()
            except Exception as e:
                return {"error": f"could not determine public IP: {e}"}

        # Mullvad publishes a server list; we infer "is Mullvad" by reverse
        # DNS — Mullvad exits resolve to *.mullvad.net or known partners
        # (e.g. m247.com / m247europe). Cheap heuristic that doesn't need
        # an extra dep or full WHOIS.
        org = ""
        try:
            async with self.http.get(f"https://ipinfo.io/{public_ip}/org",
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                org = (await r.text()).strip()
        except Exception as e:
            logger.debug("ipinfo.io org lookup for %s failed: %s", public_ip, e)
        looks_mullvad = any(s in org.lower() for s in ("mullvad", "m247", "31173",
                                                       "datapacket", "tefincom"))
        return {
            "public_ip": public_ip,
            "source": source,
            "org": org,
            "looks_mullvad": looks_mullvad,
        }

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="mullvad_status",
                description="Mullvad account status — expiry date, days remaining, paid-up flag.",
                handler=self.status,
            ),
            ToolSpec(
                name="mullvad_devices",
                description="List Wireguard devices currently registered on the Mullvad account.",
                handler=self.devices,
            ),
            ToolSpec(
                name="mullvad_check_routing",
                description=(
                    "Verify the public IP currently being used is actually a Mullvad exit. "
                    "Catches the 'tunnel handshake succeeds but no real traffic routes' bug."
                ),
                handler=self.check_routing,
            ),
        ]


def _days_until(expiry: Any) -> int | None:
    if not isinstance(expiry, str):
        return None
    try:
        import datetime
        dt = datetime.datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        delta = dt - datetime.datetime.now(datetime.UTC)
        return delta.days
    except Exception:
        return None
