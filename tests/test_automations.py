"""HA-style automation engine — trigger matching, args templating, throttling."""
import asyncio

import pytest

from homelab_ai.agent.modules import Finding, Severity
from homelab_ai.automations.engine import AutomationEngine, Rule, matches, render_args
from homelab_ai.services.base import ToolSpec


def _finding(**kw):
    base = {"module": "service_health", "target": "sonarr",
            "severity": Severity.ERROR, "message": "down", "fix_hint": ""}
    base.update(kw)
    return Finding(**base)


def test_trigger_matches_severity_at_or_above():
    rule = Rule("r", {"severity": "WARNING"}, {})
    assert matches(rule, _finding(severity=Severity.WARNING))
    assert matches(rule, _finding(severity=Severity.ERROR))
    assert matches(rule, _finding(severity=Severity.CRITICAL))


def test_trigger_skips_below_severity():
    rule = Rule("r", {"severity": "ERROR"}, {})
    assert not matches(rule, _finding(severity=Severity.WARNING))


def test_trigger_matches_module():
    rule = Rule("r", {"module": "service_health"}, {})
    assert matches(rule, _finding())
    rule2 = Rule("r", {"module": "disk_watcher"}, {})
    assert not matches(rule2, _finding())


def test_trigger_matches_target_and_fix_hint():
    rule = Rule("r", {"target": "sonarr", "fix_hint": "restart_service"}, {})
    assert not matches(rule, _finding(fix_hint=""))
    assert matches(rule, _finding(fix_hint="restart_service"))


def test_render_args_substitutes_finding_context():
    args = render_args({"name": "{target}", "sev": "{severity}", "static": "x"},
                       _finding(target="radarr", severity=Severity.CRITICAL))
    assert args["name"] == "radarr"
    assert args["sev"] == "CRITICAL"
    assert args["static"] == "x"


def test_render_args_with_bad_placeholder_passes_through():
    """A `{nope}` template should not crash even though there's no such key."""
    args = render_args({"x": "{nope}"}, _finding())
    assert args["x"] == "{nope}"


@pytest.mark.asyncio
async def test_engine_fires_matching_rule_and_invokes_tool():
    fired = []

    async def _handler(**kw):
        fired.append(kw)
        return {"ok": True}

    services = {"x": type("S", (), {"tools": lambda self: [
        ToolSpec(name="restart_service", description="d", handler=_handler)
    ]})()}
    rules = [{
        "name": "restart_on_failure",
        "trigger": {"severity": "ERROR"},
        "action": {"tool": "restart_service", "args": {"service": "{target}"}},
    }]
    eng = AutomationEngine(rules, services)
    out = await eng.on_finding(_finding())
    assert len(out) == 1
    assert fired == [{"service": "sonarr"}]


@pytest.mark.asyncio
async def test_engine_throttles_repeated_fires():
    handler_calls = []

    async def _handler(**kw):
        handler_calls.append(kw)
        return {"ok": True}

    services = {"x": type("S", (), {"tools": lambda self: [
        ToolSpec(name="restart_service", description="d", handler=_handler)
    ]})()}
    rules = [{
        "name": "r",
        "trigger": {"severity": "ERROR"},
        "action": {"tool": "restart_service"},
        "throttle_seconds": 300,
    }]
    eng = AutomationEngine(rules, services)
    await eng.on_finding(_finding())
    await eng.on_finding(_finding())
    await eng.on_finding(_finding())
    # Throttle should clip to 1 fire.
    assert len(handler_calls) == 1


@pytest.mark.asyncio
async def test_engine_handles_unknown_tool_cleanly():
    services = {}
    rules = [{"trigger": {"severity": "ERROR"}, "action": {"tool": "nope"}}]
    eng = AutomationEngine(rules, services)
    out = await eng.on_finding(_finding())
    assert out[0]["result"].get("error") == "unknown tool nope"


@pytest.mark.asyncio
async def test_engine_with_no_rules_is_no_op():
    eng = AutomationEngine([], {})
    out = await eng.on_finding(_finding())
    assert out == []
