"""Gluetun plugin — VPN container control API.

Tools:
- gluetun_public_ip — current external IP as seen from inside the tunnel
- gluetun_vpn_status — running / paused / failed
- gluetun_servers — currently-selected server location

By default Gluetun exposes its control API on port 8000 inside the
container. Most users map that to a host port (commonly 8001). Set
`url:` accordingly.
"""
from __future__ import annotations

from .base import Service, ToolSpec


class Gluetun(Service):
    name = "gluetun"

    async def _get_safe(self, path: str) -> dict:
        try:
            return await self._get(path)
        except Exception as e:
            return {"error": str(e)[:200]}

    async def health(self) -> dict:
        r = await self._get_safe("/v1/openvpn/status")
        if "error" in r:
            return {"ok": False, "error": r["error"]}
        # status is "running" when up; "stopped" / "crashed" otherwise.
        return {"ok": r.get("status") == "running", "status": r.get("status")}

    async def public_ip(self) -> dict:
        return await self._get_safe("/v1/publicip/ip")

    async def vpn_status(self) -> dict:
        return await self._get_safe("/v1/openvpn/status")

    async def servers(self) -> dict:
        return await self._get_safe("/v1/openvpn/settings")

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="gluetun_public_ip",
                description="Get the current public IP as seen from inside the Gluetun VPN tunnel.",
                handler=self.public_ip,
            ),
            ToolSpec(
                name="gluetun_vpn_status",
                description="Gluetun OpenVPN status — running / stopped / crashed.",
                handler=self.vpn_status,
            ),
            ToolSpec(
                name="gluetun_servers",
                description="Currently configured Gluetun OpenVPN server settings.",
                handler=self.servers,
            ),
        ]
