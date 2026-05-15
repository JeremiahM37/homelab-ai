"""NUT (Network UPS Tools) plugin — battery, runtime, load via TCP 3493.

Speaks the NUT protocol directly (no extra deps). Connects to the NUT
server (`upsd`) typically running on port 3493 of whichever host has the
UPS plugged in.

Config:

    services:
      nut:
        host: 192.168.1.5
        port: 3493
        username: monuser        # optional — only needed for some commands
        password: ""
        # If a config lists `ups: name`, queries default to that UPS. If
        # omitted, the plugin lists all available UPSes.
        ups: ""

Tools exposed:
- nut_list_upses
- nut_status(ups?)        — overall status string (OL, OB, LB, etc.)
- nut_battery(ups?)       — charge %, runtime seconds, voltage
- nut_load(ups?)          — load percent + input voltage
- nut_all_vars(ups?)      — every var the UPS exposes (limited to 50)
"""
from __future__ import annotations

import asyncio
import logging

from .base import Service, ToolSpec

logger = logging.getLogger("homelab_ai.services.nut")


class NUT(Service):
    name = "nut"

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        host = self.config.get("host") or self._host_from_url()
        port = int(self.config.get("port", 3493))
        timeout = float(self.config.get("timeout", 5.0))
        return await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout,
        )

    def _host_from_url(self) -> str:
        """Allow url: nut://host:3493 or http://host:3493 in addition to host: ..."""
        url = self.config.get("url", "")
        if "://" in url:
            url = url.split("://", 1)[1]
        return url.split(":", 1)[0] or "localhost"

    async def _cmd(self, line: str) -> list[str]:
        """Send one NUT command, read until BEGIN/END or single line response."""
        reader, writer = await self._connect()
        try:
            await self._maybe_auth(reader, writer)
            writer.write((line + "\n").encode())
            await writer.drain()
            response_lines: list[str] = []
            inside_block = False
            while True:
                raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").rstrip()
                if text.startswith("BEGIN "):
                    inside_block = True
                    continue
                if text.startswith("END "):
                    break
                if text.startswith("ERR "):
                    raise RuntimeError(f"NUT error: {text}")
                response_lines.append(text)
                if not inside_block:
                    break
            return response_lines
        finally:
            import contextlib
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _maybe_auth(self, reader, writer) -> None:
        user = self.config.get("username") or ""
        pwd = self.config.get("password") or ""
        if not user:
            return
        for line in (f"USERNAME {user}", f"PASSWORD {pwd}"):
            writer.write((line + "\n").encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.readline(), timeout=3.0)
            if not resp.decode().strip().startswith("OK"):
                # Auth not strictly required for read-only — log and move on.
                logger.info("NUT auth %s response: %s", line.split()[0], resp.decode().strip())
                return

    @staticmethod
    def _parse_list_ups(lines: list[str]) -> list[dict]:
        """`UPS <name> "<description>"` per line."""
        out = []
        for ln in lines:
            if not ln.startswith("UPS "):
                continue
            parts = ln[4:].split(maxsplit=1)
            if not parts:
                continue
            name = parts[0]
            desc = parts[1].strip('"') if len(parts) > 1 else ""
            out.append({"name": name, "description": desc})
        return out

    @staticmethod
    def _parse_vars(lines: list[str]) -> dict[str, str]:
        """`VAR <ups> <name> "<value>"` per line."""
        out: dict[str, str] = {}
        for ln in lines:
            if not ln.startswith("VAR "):
                continue
            rest = ln[4:].split(maxsplit=2)
            if len(rest) < 3:
                continue
            out[rest[1]] = rest[2].strip('"')
        return out

    # ── service API ────────────────────────────────────────────────────

    async def health(self) -> dict:
        try:
            upses = await self.list_upses()
            return {"ok": True, "upses": len(upses.get("upses", []))}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def list_upses(self) -> dict:
        lines = await self._cmd("LIST UPS")
        return {"upses": self._parse_list_ups(lines)}

    async def status(self, ups: str | None = None) -> dict:
        u = ups or self.config.get("ups") or await self._first_ups()
        if not u:
            return {"error": "no UPS configured or detected"}
        lines = await self._cmd(f"GET VAR {u} ups.status")
        # Single VAR line.
        v = self._parse_vars(lines)
        return {"ups": u, "status": v.get("ups.status", "unknown")}

    async def battery(self, ups: str | None = None) -> dict:
        u = ups or self.config.get("ups") or await self._first_ups()
        if not u:
            return {"error": "no UPS configured or detected"}
        lines = await self._cmd(f"LIST VAR {u}")
        v = self._parse_vars(lines)
        return {
            "ups": u,
            "charge_percent": _to_float(v.get("battery.charge")),
            "runtime_seconds": _to_float(v.get("battery.runtime")),
            "voltage": _to_float(v.get("battery.voltage")),
            "status": v.get("ups.status"),
        }

    async def load(self, ups: str | None = None) -> dict:
        u = ups or self.config.get("ups") or await self._first_ups()
        if not u:
            return {"error": "no UPS configured or detected"}
        lines = await self._cmd(f"LIST VAR {u}")
        v = self._parse_vars(lines)
        return {
            "ups": u,
            "load_percent": _to_float(v.get("ups.load")),
            "input_voltage": _to_float(v.get("input.voltage")),
            "output_voltage": _to_float(v.get("output.voltage")),
        }

    async def all_vars(self, ups: str | None = None) -> dict:
        u = ups or self.config.get("ups") or await self._first_ups()
        if not u:
            return {"error": "no UPS configured or detected"}
        lines = await self._cmd(f"LIST VAR {u}")
        v = self._parse_vars(lines)
        # Cap output so the LLM doesn't get hundreds of vars.
        return {"ups": u, "vars": dict(list(v.items())[:50])}

    async def _first_ups(self) -> str | None:
        try:
            data = await self.list_upses()
            ups_list = data.get("upses") or []
            return ups_list[0]["name"] if ups_list else None
        except Exception:
            return None

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="nut_list_upses",
                description="List UPS units known to the NUT server.",
                handler=self.list_upses,
            ),
            ToolSpec(
                name="nut_status",
                description="Get the current ups.status string (e.g. 'OL' = on line, 'OB' = on battery, 'LB' = low battery).",
                handler=self.status,
                params={"ups": {"type": "string", "default": ""}},
            ),
            ToolSpec(
                name="nut_battery",
                description="Get UPS battery state — charge percent, remaining runtime, voltage.",
                handler=self.battery,
                params={"ups": {"type": "string", "default": ""}},
            ),
            ToolSpec(
                name="nut_load",
                description="Get UPS load percent and input/output voltage.",
                handler=self.load,
                params={"ups": {"type": "string", "default": ""}},
            ),
            ToolSpec(
                name="nut_all_vars",
                description="Get every variable the UPS exposes (capped to 50 entries).",
                handler=self.all_vars,
                params={"ups": {"type": "string", "default": ""}},
            ),
        ]


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s)
    except ValueError:
        return None
