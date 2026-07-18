"""AI agent — Ollama-backed tool-calling loop with semantic tool selection.

Endpoints:
  GET  /api/ai/tools            — full tool catalog (for debugging / MCP)
  POST /api/ai/agent            — one-shot agent call, returns final answer
  POST /api/ai/agent/stream     — SSE stream of {type, ...} chunks
  POST /api/ai/embed            — expose the embedding model

The agent loop is intentionally small: at most `max_tool_iterations`
rounds, then we force a final answer (no tools) so we never hang.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from homelab_ai.llm import get_client, get_model
from homelab_ai.llm.ollama import tool_to_openai_function

logger = logging.getLogger("homelab_ai.api.ai")
router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_TOOL_ITERATIONS = 6
# If the LLM calls the same tool with identical arguments more than this many
# times in a single conversation we stop and force a final answer.
MAX_SAME_CALL = 2
# Truncate tool results that are larger than this before feeding back to the
# LLM (it tends to derail when handed multi-KB JSON).
MAX_TOOL_RESULT_CHARS = 4000

SYSTEM_PROMPT = (
    "You are a homelab assistant. You have a catalog of tools that wrap real "
    "services on the user's network — call them when relevant. Stay concise. "
    "If a tool's result already answers the question, return that answer "
    "directly without paraphrasing the whole payload. Refuse requests that "
    "would push to git, post to external services, or delete files."
)


def _collect_tools(services: dict) -> list[dict]:
    """Build a flat list of {service, name, description, schema, handler} dicts."""
    out = []
    for svc_name, svc in services.items():
        for t in svc.tools():
            out.append({
                "service": svc_name,
                "name": t.name,
                "description": t.description,
                "schema": t.json_schema(),
                "handler": t.handler,
                "params": {
                    k: {kk: vv for kk, vv in v.items() if kk != "required"}
                    for k, v in t.params.items()
                },
            })
    return out


@router.get("/tools")
async def list_tools(request: Request):
    """Full tool catalog (name, description, schema) across all services."""
    tools = _collect_tools(request.app.state.services)
    # Strip handler before serializing.
    return {
        "tools": [
            {k: v for k, v in t.items() if k != "handler"}
            for t in tools
        ],
    }


@router.post("/embed")
async def embed(request: Request, body: dict = Body(...)) -> dict:
    """Embed text with the configured (or requested) embedding model."""
    text = body.get("text") or ""
    cfg = request.app.state.cfg
    model = body.get("model") or get_model(cfg, "embed")
    if not text:
        raise HTTPException(400, "text required")
    client = get_client(cfg, request.app.state.http)
    try:
        emb = await client.embed(model, text)
        return {"model": model, "dim": len(emb), "embedding": emb}
    except aiohttp.ClientError as e:
        raise HTTPException(502, f"LLM backend unreachable: {e}")


async def _run_tool(tool: dict, arguments: dict) -> Any:
    """Execute one tool call, mapping tool errors to an {'error': ...} result."""
    handler: Callable[..., Awaitable[Any]] = tool["handler"]
    try:
        return await handler(**(arguments or {}))
    except TypeError as e:
        # LLM passed unexpected args — give it back a hint instead of crashing.
        return {"error": f"bad arguments: {e}"}
    except Exception as e:
        logger.warning("tool %s raised: %s", tool["name"], e)
        return {"error": f"{type(e).__name__}: {e}"}


async def _select_tools(request: Request, query: str, all_tools: list[dict],
                        k: int = 16) -> list[dict]:
    """Pick the top-k relevant tools.

    Uses the embedding-backed router if it's warm; falls back to keyword
    overlap if Ollama isn't reachable or the catalog is small.
    """
    if len(all_tools) <= k:
        return all_tools
    router = getattr(request.app.state, "tool_router", None)
    if router is not None:
        try:
            return await router.select(query, k=k)
        except Exception as e:
            logger.warning("semantic router failed, falling back to keyword: %s", e)

    import re
    word = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_-]+\b")
    q_tokens = {w.lower() for w in word.findall(query) if len(w) > 2}
    if not q_tokens:
        return all_tools[:k]
    scored = []
    for t in all_tools:
        text = f"{t['name']} {t['description']}"
        t_tokens = {w.lower() for w in word.findall(text) if len(w) > 2}
        overlap = len(q_tokens & t_tokens)
        scored.append((overlap, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored[0][0] == 0:
        return all_tools[:k]
    return [t for _, t in scored[:k]]


async def _agent_loop(
    request: Request,
    prompt: str,
) -> dict[str, Any]:
    """Tool-calling loop: select tools, let the LLM call them, return the final answer."""
    cfg = request.app.state.cfg
    all_tools = _collect_tools(request.app.state.services)
    selected = await _select_tools(request, prompt, all_tools)
    tool_index = {t["name"]: t for t in selected}

    client = get_client(cfg, request.app.state.http)
    small_model = get_model(cfg, "small")
    fn_tools = [
        tool_to_openai_function(t["name"], t["description"], t["schema"])
        for t in selected
    ]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    tool_calls_made: list[dict] = []
    # Track (tool_name, json-args) seen this conversation to break loops.
    seen_calls: dict[tuple, int] = {}

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Always non-streaming here; we re-stream the final answer at the end.
        # Tool-calling chunked streaming is messy across Ollama versions and
        # adds little value when we have to wait for tool results anyway.
        try:
            resp = await client.chat(
                small_model,
                messages,
                tools=fn_tools,
                stream=False,
                think=False,
            )
        except aiohttp.ClientError as e:
            return {"answer": f"LLM unreachable: {e}", "error": str(e), "tool_calls": tool_calls_made}

        msg = resp.get("message", {})
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = (msg.get("content") or "").strip()
            return {
                "answer": answer or "(empty response)",
                "model": small_model,
                "tool_calls": tool_calls_made,
                "iterations": iteration + 1,
            }

        messages.append(msg)
        looped = False
        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            sig = (name, json.dumps(args, sort_keys=True, default=str))
            seen_calls[sig] = seen_calls.get(sig, 0) + 1
            if seen_calls[sig] > MAX_SAME_CALL:
                looped = True
                tool_result = {"error": "duplicate call suppressed — answer with the data you already have"}
            else:
                tool = tool_index.get(name)
                if not tool:
                    tool_result = {"error": f"unknown tool {name!r}"}
                else:
                    tool_result = await _run_tool(tool, args)
            tool_calls_made.append({"name": name, "arguments": args, "result": tool_result})
            payload = json.dumps(tool_result, default=str)
            if len(payload) > MAX_TOOL_RESULT_CHARS:
                payload = payload[:MAX_TOOL_RESULT_CHARS] + f"\n…(truncated {len(payload)-MAX_TOOL_RESULT_CHARS} chars)"
            messages.append({"role": "tool", "content": payload})
        if looped:
            # Force a final-answer round with no tools.
            break

    # Iteration cap reached — force a final answer with no tools.
    try:
        final = await client.chat(
            small_model,
            messages + [{"role": "user", "content": "Summarize the result above in 1-3 sentences."}],
            tools=None,
            stream=False,
            think=False,
        )
        answer = (final.get("message", {}).get("content") or "(no answer)").strip()
    except aiohttp.ClientError as e:
        answer = f"LLM unreachable during summary: {e}"
    return {
        "answer": answer,
        "model": small_model,
        "tool_calls": tool_calls_made,
        "iterations": MAX_TOOL_ITERATIONS,
        "capped": True,
    }


@router.post("/agent")
async def agent_chat(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """One-shot agent call: {"prompt": "..."} → {"answer": "...", "tool_calls": [...]}"""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    return await _agent_loop(request, prompt)


@router.post("/agent/stream")
async def agent_chat_stream(request: Request, body: dict = Body(...)):
    """SSE stream of {type, ...} events. Events: tool_call, tool_result, answer."""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")

    async def gen():
        result = await _agent_loop(request, prompt)
        for tc in result.get("tool_calls", []):
            yield f"event: tool_call\ndata: {json.dumps(tc, default=str)}\n\n"
            await asyncio.sleep(0)
        yield f"event: answer\ndata: {json.dumps({'answer': result.get('answer','')})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
