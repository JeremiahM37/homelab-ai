# Adding your own tool

If you just want to expose a single function to the AI agent — not a full service — you have two options.

## Option 1 — Drop a tool into an existing service

Find the closest matching service plugin and add to its `tools()` method. This is the right call for service-specific actions (e.g. "search Jellyfin by genre").

## Option 2 — Standalone tool

If your tool doesn't naturally belong to one service (e.g. weather lookup, currency conversion, send-to-kindle), use the standalone tool pattern:

```python
# ~/.config/homelab-ai/tools/weather.py
from homelab_ai.mcp.decorators import tool

@tool(description="Get the current temperature for a city.")
async def get_weather(city: str) -> dict:
    # Your implementation. Async functions only.
    return {"city": city, "temp_c": 22}
```

Tools registered this way show up in the AI catalog (`/api/ai/tools`) and the MCP server. They run in the homelab-ai process and have whatever access the process has.

## Tool design

- **One verb per tool.** `download_movie` and `search_movies` are two tools, not one with a `mode` parameter.
- **Stable inputs.** LLMs do better with positional-style args than nested objects. `search_movies(query: str, year: int | None = None)` beats `search_movies(filters: dict)`.
- **Idempotent.** Calling the same tool twice with the same input should be safe. Side-effectful tools (sending Discord messages, deleting files) should make the side effect part of the description: *"Send a notification to Discord (writes to the configured webhook)"*.
- **Short description.** The semantic router embeds the description. One sentence, action-first. *"Search Jellyfin by title and return the top 10 matches."*

## Secrets in tools

If your tool needs an API key, read it from the same config the service plugins use:

```python
import os

@tool(description="...")
async def my_tool() -> dict:
    api_key = os.environ.get("MY_API_KEY")
    if not api_key:
        return {"error": "MY_API_KEY not set"}
    ...
```

Don't hard-code secrets, even in user plugins — your `~/.config/` is in someone's backups eventually.

## Forbidden tools

Tools may not:

- `git push`, `gh pr ...` (any GitHub write)
- Send external messages without user-facing acknowledgement
- Delete files outside `data/`
- Modify their own source

These limits are conventions, not enforced sandboxing. The Tier-3 fixer's safety properties (snapshot + audit + caps) protect file edits the **fixer** makes; standalone tools are trusted code you wrote yourself.
