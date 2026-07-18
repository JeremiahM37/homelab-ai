"""Declarative REST service plugin — the "blueprint" for any new service.

A user can wire up support for any HTTP-JSON service without writing
Python, just by adding a config block:

    services:
      my_thing:                   # ← service name, free choice
        plugin: generic_http      # ← tells the loader to use this class
        url: http://my-thing:8080
        auth:
          type: bearer             # bearer | header | basic | query | none
          key: ${MY_TOKEN}
        health:
          path: /healthz
          method: GET
          ok_if:
            status_lt: 400         # default
            body_contains: "ok"    # optional substring
        tools:
          - name: list_things
            description: List things from my service
            path: /api/things
            method: GET
            params:
              limit: {type: integer, default: 10, in: query}

          - name: get_thing
            description: Get a specific thing
            path: /api/things/{id}        # {placeholders} substituted from args
            params:
              id: {type: string, required: true, in: path}

          - name: create_thing
            description: Create
            path: /api/things
            method: POST
            params:
              name: {type: string, required: true, in: body}
            response:
              extract: data.id            # dot path; default returns full JSON

Existing Python plugins (sonarr.py, jellyfin.py, nut.py, etc.) remain the
*finished build*. This is the *blueprint* for everything else — anyone with
a YAML editor can add a service without a PR.

Limits (intentional — declarative DSLs grow into half-baked languages
otherwise):
- Single-request flows only. Multi-step (e.g. qBittorrent's login → cookie →
  call) require a Python plugin.
- Response extraction is a flat dot path (`data.items`). Array slicing,
  JMESPath, or jq are out of scope; copy the JSON shape into a real plugin
  if you need them.
- No retry / circuit-breaker logic. Falls through aiohttp's defaults.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import aiohttp

from .base import Service, ToolSpec

logger = logging.getLogger("homelab_ai.services.generic_http")


class GenericHTTP(Service):
    """Declarative service driven entirely by the config block.

    Subclassing is supported but not required — the whole point is that
    users don't need to touch Python.
    """
    name = "generic_http"

    # ── auth ────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        a = self.config.get("auth") or {}
        atype = (a.get("type") or "none").lower()
        if atype == "bearer":
            return {"Authorization": f"Bearer {a.get('key', '')}"}
        if atype == "header":
            return {a.get("header_name", "X-Api-Key"): a.get("value") or a.get("key", "")}
        return {}

    def _auth_basic(self) -> aiohttp.BasicAuth | None:
        a = self.config.get("auth") or {}
        if (a.get("type") or "").lower() == "basic":
            return aiohttp.BasicAuth(a.get("username", ""), a.get("password", ""))
        return None

    def _auth_query(self) -> dict[str, str]:
        a = self.config.get("auth") or {}
        if (a.get("type") or "").lower() == "query":
            return {a.get("query_name", "apikey"): a.get("value") or a.get("key", "")}
        return {}

    # ── health ──────────────────────────────────────────────────────────

    async def health(self) -> dict:
        h = self.config.get("health") or {}
        path = h.get("path", "/")
        method = (h.get("method") or "GET").upper()
        try:
            status, body = await self._raw_request(method, path)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

        ok_if = h.get("ok_if") or {}
        # Default: ok iff status < 400. Users can override via ok_if.status_lt
        # or ok_if.status; an explicit value wins.
        status_lt = ok_if.get("status_lt", 400)
        exact_status = ok_if.get("status")
        ok = status < status_lt
        if exact_status is not None:
            ok = status == exact_status
        if (sub := ok_if.get("body_contains")) and sub.lower() not in (body or "").lower():
            ok = False

        return {"ok": ok, "status": status}

    # ── tools ────────────────────────────────────────────────────────────

    def tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        svc_name = self.config.get("name") or "service"
        for tdef in self.config.get("tools") or []:
            if not isinstance(tdef, dict) or not tdef.get("name") or not tdef.get("path"):
                logger.warning("generic_http %s: tool missing name/path: %r", svc_name, tdef)
                continue
            try:
                out.append(self._build_tool(tdef))
            except Exception as e:
                logger.warning("generic_http %s: failed to build tool %s: %s",
                               svc_name, tdef.get("name"), e)
        return out

    def _build_tool(self, tdef: dict) -> ToolSpec:
        params = tdef.get("params") or {}
        handler = self._make_handler(tdef)
        # Strip homelab-ai-specific keys before exposing to the LLM schema.
        clean_params = {
            k: {kk: vv for kk, vv in v.items() if kk != "in"}
            for k, v in params.items() if isinstance(v, dict)
        }
        return ToolSpec(
            name=tdef["name"],
            description=tdef.get("description", ""),
            handler=handler,
            params=clean_params,
        )

    def _make_handler(self, tdef: dict):
        path_template = tdef["path"]
        method = (tdef.get("method") or "GET").upper()
        params_def = tdef.get("params") or {}
        body_template = tdef.get("body_template")
        response_def = tdef.get("response") or {}

        async def _handler(**kwargs):
            # Route args into path / query / body / header per the param def.
            path_args: dict[str, Any] = {}
            query: dict[str, Any] = {}
            body: dict[str, Any] = {}
            headers: dict[str, str] = {}

            for pname, pdef in params_def.items():
                if not isinstance(pdef, dict):
                    continue
                if pname in kwargs:
                    val = kwargs[pname]
                elif "default" in pdef:
                    val = pdef["default"]
                else:
                    if pdef.get("required"):
                        return {"error": f"missing required parameter: {pname}"}
                    continue
                where = pdef.get("in")
                if where is None:
                    where = "query" if method == "GET" else "body"
                if where == "path":
                    path_args[pname] = val
                elif where == "query":
                    query[pname] = val
                elif where == "body":
                    body[pname] = val
                elif where == "header":
                    headers[pname] = str(val)

            try:
                path = _format_path(path_template, path_args)
            except KeyError as e:
                return {"error": f"path template missing arg: {e}"}

            # body_template overrides per-param body collection if present.
            if body_template is not None:
                try:
                    body = _format_template(body_template, kwargs)
                except KeyError as e:
                    return {"error": f"body template missing arg: {e}"}

            try:
                status, parsed = await self._raw_json_request(
                    method, path, query=query, body=body or None, extra_headers=headers,
                )
            except Exception as e:
                return {"error": f"{type(e).__name__}: {e}"}

            if status >= 400:
                return {"error": f"HTTP {status}", "body": parsed}

            extract_path = response_def.get("extract")
            if extract_path:
                return {"result": _dot_extract(parsed, extract_path)}
            return parsed if isinstance(parsed, (dict, list)) else {"result": parsed}

        return _handler

    # ── HTTP plumbing ───────────────────────────────────────────────────

    async def _raw_request(self, method: str, path: str) -> tuple[int, str]:
        url = self.config["url"].rstrip("/") + path
        headers = self._auth_headers()
        kwargs: dict[str, Any] = {"headers": headers}
        if auth := self._auth_basic():
            kwargs["auth"] = auth
        if q := self._auth_query():
            kwargs["params"] = q
        async with self.http.request(method, url, **kwargs) as r:
            return r.status, await r.text()

    async def _raw_json_request(
        self, method: str, path: str,
        query: dict | None = None, body: dict | None = None,
        extra_headers: dict | None = None,
    ) -> tuple[int, Any]:
        url = self.config["url"].rstrip("/") + path
        headers = {**self._auth_headers(), **(extra_headers or {}),
                   "Accept": "application/json"}
        kwargs: dict[str, Any] = {"headers": headers}
        if auth := self._auth_basic():
            kwargs["auth"] = auth
        params = dict(query or {})
        params.update(self._auth_query())
        if params:
            kwargs["params"] = params
        if body is not None and method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = body
        async with self.http.request(method, url, **kwargs) as r:
            text = await r.text()
            try:
                import json as _json
                parsed = _json.loads(text) if text else None
            except Exception as e:
                logger.debug("%s %s: non-JSON response (%s), returning raw text",
                             method, url, e)
                parsed = text
            return r.status, parsed


# ── helpers ──────────────────────────────────────────────────────────────

def _format_path(template: str, args: dict) -> str:
    """Substitute {key} placeholders. URL-encodes path segments to avoid
    injection or accidental slashes."""
    if "{" not in template:
        return template
    out = template
    for k, v in args.items():
        encoded = urllib.parse.quote(str(v), safe="")
        if "{" + k + "}" not in out:
            raise KeyError(k)
        out = out.replace("{" + k + "}", encoded)
    if "{" in out and "}" in out:
        # Unfilled placeholder — surface as a clear error.
        missing = out[out.index("{") + 1: out.index("}", out.index("{"))]
        raise KeyError(missing)
    return out


def _format_template(template: Any, args: dict) -> Any:
    """Recursively substitute {key} placeholders inside a nested dict/list."""
    if isinstance(template, str):
        if "{" not in template:
            return template
        try:
            return template.format(**args)
        except (KeyError, IndexError) as e:
            raise KeyError(str(e)) from e
    if isinstance(template, dict):
        return {k: _format_template(v, args) for k, v in template.items()}
    if isinstance(template, list):
        return [_format_template(v, args) for v in template]
    return template


def _dot_extract(obj: Any, path: str) -> Any:
    """Walk a dot path through nested dicts/lists. Returns None on miss.

    Supported:
      data.items           → obj["data"]["items"]
      data.items.0.name    → obj["data"]["items"][0]["name"]
    """
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur
