"""Failure memory dedup + cooldown."""
from pathlib import Path

from homelab_ai.agent.failure_memory import FailureMemory


def test_dedup_same_fingerprint(tmp_path: Path):
    mem = FailureMemory(tmp_path / "test.db")
    a = mem.record("mod", "tgt", "boom")
    b = mem.record("mod", "tgt", "boom")
    assert a["fingerprint"] == b["fingerprint"]
    assert b["seen_count"] == 2


def test_distinct_target_distinct_fp(tmp_path: Path):
    mem = FailureMemory(tmp_path / "t.db")
    a = mem.record("mod", "t1", "boom")
    b = mem.record("mod", "t2", "boom")
    assert a["fingerprint"] != b["fingerprint"]


def test_cooldown_blocks_repeat_fix(tmp_path: Path):
    mem = FailureMemory(tmp_path / "t.db")
    row = mem.record("mod", "tgt", "boom")
    fp = row["fingerprint"]
    assert mem.should_skip(fp) is False  # never fixed → not in cooldown
    mem.mark_fix_attempt(fp, tier=1)
    assert mem.should_skip(fp, cooldown_seconds=300) is True


def test_resolution_clears_open_list(tmp_path: Path):
    mem = FailureMemory(tmp_path / "t.db")
    row = mem.record("mod", "tgt", "boom")
    assert len(mem.open_failures()) == 1
    mem.mark_resolved(row["fingerprint"])
    assert len(mem.open_failures()) == 0
