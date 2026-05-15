"""History store — scans, AI calls, fixes."""
import time

import pytest

from homelab_ai.history import HistoryStore


def test_record_and_retrieve_scan(tmp_path):
    s = HistoryStore(tmp_path / "h.db")
    s.record_scan({"findings": 3, "fixed": 1})
    out = s.recent_scans(limit=10)
    assert len(out) == 1
    assert out[0]["summary"]["findings"] == 3


def test_record_ai_call_truncates_payload(tmp_path):
    s = HistoryStore(tmp_path / "h.db")
    big = "x" * 20000
    s.record_ai_call("m", big, big, [{"name": "t"}], 1234)
    out = s.recent_ai_calls(limit=1)[0]
    assert out["model"] == "m"
    assert len(out["prompt"]) <= 8000
    assert out["duration_ms"] == 1234


def test_record_fix(tmp_path):
    s = HistoryStore(tmp_path / "h.db")
    s.record_fix("sonarr", tier=2, outcome="ok", detail="restart succeeded")
    out = s.recent_fixes(limit=1)[0]
    assert out["target"] == "sonarr"
    assert out["tier"] == 2
    assert out["outcome"] == "ok"


def test_prune_old_rows(tmp_path):
    s = HistoryStore(tmp_path / "h.db", keep_days=1)
    s.record_scan({"x": 1})
    # Force the row's timestamp to a week ago — older than keep_days=1.
    s.conn.execute("UPDATE scans SET ts = ts - 7*86400")
    s.conn.commit()
    s._prune()
    assert len(s.recent_scans()) == 0


def test_keep_days_zero_disables_pruning(tmp_path):
    s = HistoryStore(tmp_path / "h.db", keep_days=0)
    s.record_scan({"x": 1})
    s.conn.execute("UPDATE scans SET ts = 0")
    s.conn.commit()
    s._prune()
    # Sentinel — keep_days <= 0 means "don't prune anything".
    assert len(s.recent_scans()) == 1


def test_recent_scans_order_newest_first(tmp_path):
    s = HistoryStore(tmp_path / "h.db")
    s.record_scan({"i": 1})
    time.sleep(0.01)
    s.record_scan({"i": 2})
    out = s.recent_scans(limit=10)
    assert out[0]["summary"]["i"] == 2
    assert out[1]["summary"]["i"] == 1
