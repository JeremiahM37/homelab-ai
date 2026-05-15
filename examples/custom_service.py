"""Example user service plugin — drop this into ~/.config/homelab-ai/services/.

This shows the absolute minimum: a health check that hits an HTTP endpoint
plus one tool the AI agent / MCP server can call. Copy + rename + adapt.
"""
from homelab_ai.services.base import Service, ToolSpec


class HelloService(Service):
    name = "hello"

    async def health(self) -> dict:
        try:
            r = await self._get("/healthz")
            return {"ok": True, "detail": r.get("status", "ok")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def say_hello(self, name: str = "world") -> dict:
        return {"greeting": f"hello, {name}!"}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="hello_say_hello",
                description="Return a greeting message. Useful for verifying the tool surface is wired up.",
                handler=self.say_hello,
                params={"name": "string (default 'world')"},
            ),
        ]
