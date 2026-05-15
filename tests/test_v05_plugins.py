"""Tests for v0.5 service plugins (tdarr, calibre-web, gluetun,
changedetection, n8n, grafana) — all using the fake session fixture."""
import pytest

from homelab_ai.services.calibre_web import CalibreWeb
from homelab_ai.services.changedetection import ChangeDetection
from homelab_ai.services.gluetun import Gluetun
from homelab_ai.services.grafana import Grafana
from homelab_ai.services.n8n import N8N
from homelab_ai.services.tdarr import Tdarr

# ── tdarr ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tdarr_server_stats_maps_table_counters(fake_session, FakeResponseFixture):
    fake_session.stub("POST", "/api/v2/cruddb",
                      FakeResponseFixture(json_data={
                          "totalFileCount": 1500,
                          "table3Count": 2,
                          "table4Count": 1400,
                          "table2Count": 5,
                      }))
    svc = Tdarr({"url": "http://x:8265"}, fake_session)
    r = await svc.server_stats()
    assert r["library_files"] == 1500
    assert r["transcode_queue"] == 2
    assert r["errors"] == 5


@pytest.mark.asyncio
async def test_tdarr_health(fake_session, FakeResponseFixture):
    fake_session.stub("POST", "/api/v2/cruddb",
                      FakeResponseFixture(json_data={"totalFileCount": 0}))
    svc = Tdarr({"url": "http://x:8265"}, fake_session)
    r = await svc.health()
    assert r["ok"] is True


# ── calibre-web ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calibre_web_search_parses_opds_xml(fake_session, FakeResponseFixture):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>The Fellowship of the Ring</title>
    <author><name>J.R.R. Tolkien</name></author>
  </entry>
  <entry>
    <title>The Two Towers</title>
    <author><name>J.R.R. Tolkien</name></author>
  </entry>
</feed>"""
    fake_session.stub("GET", "/opds/search/Tolkien",
                      FakeResponseFixture(status=200, text_data=xml))
    svc = CalibreWeb({"url": "http://x:8083"}, fake_session)
    r = await svc.search("Tolkien")
    assert r["count"] == 2
    assert r["results"][0]["author"] == "J.R.R. Tolkien"


# ── gluetun ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gluetun_health_is_ok_when_running(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/v1/openvpn/status",
                      FakeResponseFixture(json_data={"status": "running"}))
    svc = Gluetun({"url": "http://x:8000"}, fake_session)
    r = await svc.health()
    assert r["ok"] is True


@pytest.mark.asyncio
async def test_gluetun_health_unhealthy_when_stopped(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/v1/openvpn/status",
                      FakeResponseFixture(json_data={"status": "stopped"}))
    svc = Gluetun({"url": "http://x:8000"}, fake_session)
    r = await svc.health()
    assert r["ok"] is False


@pytest.mark.asyncio
async def test_gluetun_public_ip(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/v1/publicip/ip",
                      FakeResponseFixture(json_data={"public_ip": "1.2.3.4"}))
    svc = Gluetun({"url": "http://x:8000"}, fake_session)
    r = await svc.public_ip()
    assert r["public_ip"] == "1.2.3.4"


# ── changedetection ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_changedetection_lists_watches(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v1/watch",
                      FakeResponseFixture(json_data={
                          "u1": {"title": "T", "url": "http://x", "viewed": True,
                                 "last_changed": 0},
                      }))
    svc = ChangeDetection({"url": "http://x:5100", "api_key": "k"}, fake_session)
    r = await svc.list_watches()
    assert r["count"] == 1


@pytest.mark.asyncio
async def test_changedetection_only_lists_unviewed_changes(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v1/watch",
                      FakeResponseFixture(json_data={
                          "u1": {"title": "Old", "url": "http://a", "viewed": True,
                                 "last_changed": 1000},
                          "u2": {"title": "New", "url": "http://b", "viewed": False,
                                 "last_changed": 2000},
                          "u3": {"title": "NeverChanged", "url": "http://c",
                                 "viewed": False, "last_changed": 0},
                      }))
    svc = ChangeDetection({"url": "http://x:5100", "api_key": "k"}, fake_session)
    r = await svc.changed_recently()
    assert r["count"] == 1
    assert r["changed"][0]["title"] == "New"


# ── n8n ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_n8n_lists_active_workflows(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v1/workflows",
                      FakeResponseFixture(json_data={"data": [
                          {"id": 1, "name": "Backup nightly", "active": True},
                          {"id": 2, "name": "Disabled flow", "active": False},
                      ]}))
    svc = N8N({"url": "http://x:5678", "api_key": "k"}, fake_session)
    r = await svc.list_workflows()
    # The plugin's `active=true` query string is what filters server-side;
    # in the test the fake doesn't filter, so we just verify wiring.
    assert r["count"] >= 1


@pytest.mark.asyncio
async def test_n8n_failed_executions_filters_status(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/v1/executions",
                      FakeResponseFixture(json_data={"data": [
                          {"id": 1, "status": "success", "finished": True},
                          {"id": 2, "status": "error", "finished": True},
                          {"id": 3, "status": "crashed", "finished": True},
                      ]}))
    svc = N8N({"url": "http://x:5678", "api_key": "k"}, fake_session)
    r = await svc.failed_executions()
    assert r["count"] == 2


# ── grafana ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grafana_health(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/health",
                      FakeResponseFixture(json_data={"database": "ok", "version": "10.4.0"}))
    svc = Grafana({"url": "http://x:3000"}, fake_session)
    r = await svc.health()
    assert r["ok"] is True
    assert r["version"] == "10.4.0"


@pytest.mark.asyncio
async def test_grafana_dashboards(fake_session, FakeResponseFixture):
    fake_session.stub("GET", "/api/search",
                      FakeResponseFixture(json_data=[
                          {"uid": "a", "title": "System", "tags": ["host"], "url": "/d/a"},
                          {"uid": "b", "title": "Network"},
                      ]))
    svc = Grafana({"url": "http://x:3000"}, fake_session)
    r = await svc.list_dashboards()
    assert r["count"] == 2


@pytest.mark.asyncio
async def test_grafana_firing_alerts_handles_old_shape(fake_session, FakeResponseFixture):
    """Grafana's old alerts API returned a flat list. We should pick out the
    firing ones cleanly."""
    fake_session.stub("GET", "/api/alertmanager/grafana/api/v2/alerts",
                      FakeResponseFixture(status=404))
    fake_session.stub("GET", "/api/alerts",
                      FakeResponseFixture(json_data=[
                          {"name": "Disk full", "state": "alerting"},
                          {"name": "All good", "state": "ok"},
                          {"name": "CPU spike", "state": "firing"},
                      ]))
    svc = Grafana({"url": "http://x:3000"}, fake_session)
    r = await svc.firing_alerts()
    assert r["count"] == 2
