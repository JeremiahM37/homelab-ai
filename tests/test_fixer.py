"""Fixer subsystem — backups, audit, scope checks."""

import pytest

from homelab_ai.fixer.audit import AuditLog
from homelab_ai.fixer.backup import FileBackup


def test_audit_log_creates_header(tmp_path):
    AuditLog(tmp_path / "audit.md")
    content = (tmp_path / "audit.md").read_text()
    assert "# Homelab-AI Audit Log" in content


def test_audit_log_records_action(tmp_path):
    log = AuditLog(tmp_path / "audit.md")
    log.record(action="restart_service", target="sonarr", rationale="health 500",
               diff="-old\n+new", backup_id="abc")
    txt = (tmp_path / "audit.md").read_text()
    assert "restart_service" in txt
    assert "sonarr" in txt
    assert "abc" in txt
    assert "+new" in txt


def test_file_backup_roundtrip(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("original")
    backup_dir = tmp_path / "backups"
    fb = FileBackup(backup_dir)
    bid = fb.snapshot(src)
    src.write_text("modified")
    restored = fb.restore(bid)
    assert restored.read_text() == "original"


def test_file_backup_lists(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("x")
    fb = FileBackup(tmp_path / "b")
    fb.snapshot(src)
    fb.snapshot(src)  # idempotent enough — second snapshot is fine
    listed = fb.list()
    assert len(listed) >= 1


def test_file_backup_missing_source(tmp_path):
    fb = FileBackup(tmp_path / "b")
    with pytest.raises(FileNotFoundError):
        fb.snapshot(tmp_path / "nope.txt")


@pytest.mark.asyncio
async def test_smart_fixer_rejects_path_outside_root(tmp_path, tmp_config):
    """SmartFixer must refuse to edit files outside its edit_root."""
    import aiohttp

    from homelab_ai.agent.modules import Finding, Severity
    from homelab_ai.fixer.tier3_smart import SmartFixer

    tmp_config._raw = {"agent": {"fixer": {"edit_root": str(tmp_path / "scope")}}}
    (tmp_path / "scope").mkdir()
    (tmp_path / "evil.txt").write_text("untouchable")

    async with aiohttp.ClientSession() as http:
        fixer = SmartFixer(tmp_config, http)
        # Stub the LLM to propose editing a path outside the scope.
        async def fake_plan(*a, **kw):
            return {
                "files_to_edit": [{"path": str(tmp_path / "evil.txt"),
                                   "new_content": "owned"}],
                "rationale": "test",
            }
        fixer._invoke_smart_llm = fake_plan
        result = await fixer.attempt_fix(Finding(module="m", target="t",
                                                  severity=Severity.ERROR, message="x"))
    assert result["ok"] is False
    assert "outside edit_root" in result["detail"]
    assert (tmp_path / "evil.txt").read_text() == "untouchable"


@pytest.mark.asyncio
async def test_smart_fixer_enforces_file_cap(tmp_path, tmp_config):
    """Caps must reject over-large plans."""
    import aiohttp

    from homelab_ai.agent.modules import Finding, Severity
    from homelab_ai.fixer.tier3_smart import SmartFixer

    tmp_config._raw = {"agent": {"fixer": {"edit_root": str(tmp_path)}}}
    tmp_config.agent.fixer.max_files_changed_per_fix = 1

    async with aiohttp.ClientSession() as http:
        fixer = SmartFixer(tmp_config, http)
        async def fake_plan(*a, **kw):
            return {
                "files_to_edit": [
                    {"path": str(tmp_path / "a.txt"), "new_content": "a"},
                    {"path": str(tmp_path / "b.txt"), "new_content": "b"},
                ],
                "rationale": "test",
            }
        fixer._invoke_smart_llm = fake_plan
        result = await fixer.attempt_fix(Finding(module="m", target="t",
                                                  severity=Severity.ERROR, message="x"))
    assert result["ok"] is False
    assert "max_files_changed_per_fix" in result["detail"]
