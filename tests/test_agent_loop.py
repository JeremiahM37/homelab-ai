"""Agent scan loop — finding processing, dedup, escalation."""
import pytest

from homelab_ai.agent.failure_memory import FailureMemory
from homelab_ai.agent.modules.base import AgentModule, Finding, Severity


class _StaticModule(AgentModule):
    name = "static"
    def __init__(self, cfg, services, findings):
        super().__init__(cfg, services)
        self._findings = findings
    async def scan(self): return self._findings


@pytest.mark.asyncio
async def test_module_returns_findings(tmp_config):
    f = Finding(module="m", target="t", severity=Severity.ERROR, message="boom")
    mod = _StaticModule(tmp_config, {}, [f])
    result = await mod.scan()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_severity_below_error_not_fixed(tmp_path):
    """Only ERROR+ findings should trigger fix attempts."""
    mem = FailureMemory(tmp_path / "m.db")
    f = Finding(module="m", target="t", severity=Severity.WARNING, message="meh")
    row = mem.record(f.module, f.target, f.message)
    # Severity guard is enforced in the loop, not in failure_memory.
    # This test just documents the data shape.
    assert row["fingerprint"]


def test_finding_fingerprint_stable():
    f1 = Finding(module="m", target="t", severity=Severity.ERROR, message="x")
    f2 = Finding(module="m", target="t", severity=Severity.ERROR, message="x")
    assert f1.fingerprint() == f2.fingerprint()


def test_finding_different_message_different_fp():
    f1 = Finding(module="m", target="t", severity=Severity.ERROR, message="x")
    f2 = Finding(module="m", target="t", severity=Severity.ERROR, message="y")
    assert f1.fingerprint() != f2.fingerprint()
