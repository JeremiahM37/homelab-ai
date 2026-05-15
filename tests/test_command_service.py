"""CommandService — shell command tool generation."""

import pytest

from homelab_ai.services.command import CommandService


@pytest.mark.asyncio
async def test_runs_simple_command():
    svc = CommandService({"commands": [
        {"name": "echo_hi", "description": "Say hi", "shell": "echo hi"}
    ]}, None)
    tools = svc.tools()
    assert len(tools) == 1
    assert tools[0].name == "command_echo_hi"
    result = await tools[0].handler()
    assert result["exit_code"] == 0
    assert "hi" in result["stdout"]


@pytest.mark.asyncio
async def test_rejects_templated_command():
    """Shell strings with `{}` are refused (no LLM templating injection)."""
    svc = CommandService({"commands": [
        {"name": "bad", "description": "Bad", "shell": "rm -rf {path}"}
    ]}, None)
    tools = svc.tools()
    assert tools == []


@pytest.mark.asyncio
async def test_skips_invalid_specs():
    svc = CommandService({"commands": [
        {"name": "ok", "description": "Ok", "shell": "true"},
        {"description": "no name"},
        {"name": "no_shell"},
        "not a dict",
    ]}, None)
    tools = svc.tools()
    assert len(tools) == 1
    assert tools[0].name == "command_ok"


@pytest.mark.asyncio
async def test_health_reports_count():
    svc = CommandService({"commands": [{"name": "a", "description": "a", "shell": "true"}]}, None)
    r = await svc.health()
    assert r["ok"] is True
    assert r["commands"] == 1


@pytest.mark.asyncio
async def test_timeout_enforced():
    """A sleep longer than timeout should return an error, not hang."""
    svc = CommandService({
        "timeout_seconds": 1,
        "commands": [{"name": "slow", "description": "x", "shell": "sleep 5"}],
    }, None)
    result = await svc.tools()[0].handler()
    assert "error" in result
    assert result.get("timeout") == 1
