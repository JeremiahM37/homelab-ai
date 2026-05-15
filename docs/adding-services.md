# Adding your own service

A "service" is anything in your homelab with an HTTP API. The plugin describes how homelab-ai should monitor it and what AI-callable tools it should expose.

## Minimal plugin

Put this in `~/.config/homelab-ai/services/uptime_kuma.py`:

```python
from homelab_ai.services.base import Service, ToolSpec

class UptimeKuma(Service):
    name = "uptime_kuma"   # MUST match the key in config.yaml

    async def health(self) -> dict:
        try:
            r = await self._get("/")
            return {"ok": True, "version": "unknown"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def tools(self) -> list[ToolSpec]:
        return []  # Add later when you decide what the AI should do with it.
```

Then in `config.yaml`:

```yaml
services:
  uptime_kuma:
    url: http://uptime-kuma:3001
```

Restart homelab-ai. You'll see a row in the dashboard and `/api/overview` will report its health.

## Adding a tool

Tools are async functions the AI / MCP server can call. Keep them small, descriptive, and idempotent.

```python
class UptimeKuma(Service):
    # ...
    async def list_monitors(self) -> dict:
        r = await self._get("/api/status-page/heartbeat")
        return {"monitors": list(r.get("heartbeatList", {}).keys())}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="uptime_kuma_list_monitors",
                description="List the names of all monitors configured in Uptime Kuma.",
                handler=self.list_monitors,
            ),
        ]
```

The tool name is what the LLM sees. The description is what the semantic router embeds — make it specific. *"List names of monitors configured in Uptime Kuma"* will route correctly for prompts like "what services are we watching"; *"Get monitors"* probably won't.

## Restart handling

If your service can be recovered without operator intervention (kicking a container, calling an admin endpoint), implement `restart()`:

```python
async def restart(self) -> dict:
    # Example: hit an admin reload endpoint.
    r = await self._post("/admin/reload", headers={"Authorization": f"Bearer {self.config['admin_token']}"})
    return {"ok": True, "detail": "reload signal sent"}
```

The Tier-1 fixer will call this when `health()` returns `ok=False` and the finding carries `fix_hint="restart_service"`.

## Config keys

Whatever you read from `self.config` is taken from the matching block in `config.yaml`. No registration, no schema — just read what you need.

```yaml
services:
  uptime_kuma:
    url: http://uptime-kuma:3001
    admin_token: ${UPTIME_KUMA_TOKEN}      # env-var expansion happens before your code runs
```

```python
url = self.config["url"]
token = self.config.get("admin_token")     # use .get() if it's optional
```

## Sharing plugins

If you wrote a plugin worth sharing, open a PR adding it to `homelab_ai/services/`. Built-in plugins must:

- Use only the dependencies already in `pyproject.toml`.
- Have a `tools()` method exposing at least one useful action.
- Include a smoke test under `tests/services/` that runs without a live service (mock or skip).

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full PR checklist.
