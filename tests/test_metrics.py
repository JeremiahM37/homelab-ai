"""Prometheus metrics — registers /metrics route only when enabled."""
from fastapi.testclient import TestClient

from homelab_ai.api.main import create_app
from homelab_ai.config import Config


def _app(features=None):
    cfg = Config()
    cfg.agent.enabled = False
    cfg.services = {}
    cfg._raw = {"features": features or {}}
    return create_app(cfg)


def test_metrics_off_means_no_route():
    with TestClient(_app()) as c:
        r = c.get("/metrics")
        assert r.status_code == 404


def test_metrics_on_serves_prometheus_format():
    with TestClient(_app({"metrics": {"enabled": True}})) as c:
        r = c.get("/metrics")
        assert r.status_code == 200
        # Prometheus exposition starts with `# HELP` and/or `# TYPE` lines.
        assert "# HELP" in r.text or "# TYPE" in r.text


def test_metrics_records_counters():
    """Counters should appear in the exposition once incremented."""
    from homelab_ai.observability import metrics as m
    with TestClient(_app({"metrics": {"enabled": True}})) as c:
        c.get("/metrics")   # forces _init()
        m.record_scan("success")
        m.record_fix(1, "ok")
        m.record_ai_call("test-model", "ok")
        m.set_open_failures(3)
        m.set_service_health("sonarr", True)
        body = c.get("/metrics").text
        assert "homelab_ai_scans_total" in body
        assert "homelab_ai_fixes_total" in body
        assert "homelab_ai_open_failures 3" in body
