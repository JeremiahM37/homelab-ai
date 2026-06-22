"""Mullvad plugin — auth caching, account lookup, device list, routing check."""
import time

import pytest

from homelab_ai.services.mullvad import Mullvad, _days_until

# ── helpers ─────────────────────────────────────────────────────────────────

def test_days_until_handles_iso_with_z():
    """Mullvad's expiry comes back as `2026-06-22T11:38:52+00:00` or with Z."""
    import datetime
    future = (datetime.datetime.now(datetime.UTC) +
              datetime.timedelta(days=10))
    iso = future.isoformat().replace("+00:00", "Z")
    days = _days_until(iso)
    assert days in (9, 10)


def test_days_until_returns_none_for_garbage():
    assert _days_until(None) is None
    assert _days_until("not-a-date") is None
    assert _days_until(12345) is None


# ── auth caching ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_caches_token(fake_session, FakeResponseFixture):
    fake_session.stub("POST", "/auth/v1/token",
                      FakeResponseFixture(json_data={"access_token": "tok-1"}))
    svc = Mullvad({"account_number": "1234567812345678"}, fake_session)
    assert await svc._auth() == "tok-1"
    # Second call should reuse the cached token (not hit POST again).
    assert await svc._auth() == "tok-1"


@pytest.mark.asyncio
async def test_auth_raises_without_account(fake_session):
    svc = Mullvad({}, fake_session)
    with pytest.raises(RuntimeError, match="account_number"):
        await svc._auth()


@pytest.mark.asyncio
async def test_auth_raises_on_http_error(fake_session, FakeResponseFixture):
    fake_session.stub("POST", "/auth/v1/token",
                      FakeResponseFixture(status=401, json_data={"code": "INVALID_ACCOUNT"}))
    svc = Mullvad({"account_number": "0000000000000000"}, fake_session)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await svc._auth()


# ── account status ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_returns_expiry_and_days(fake_session, FakeResponseFixture):
    import datetime
    future = (datetime.datetime.now(datetime.UTC) +
              datetime.timedelta(days=33)).isoformat()
    fake_session.stub("POST", "/auth/v1/token",
                      FakeResponseFixture(json_data={"access_token": "t"}))
    fake_session.stub("GET", "/accounts/v1/accounts/me",
                      FakeResponseFixture(json_data={
                          "expiry": future, "max_devices": 5, "max_ports": 1,
                          "has_payments": True,
                      }))
    svc = Mullvad({"account_number": "1"*16}, fake_session)
    r = await svc.status()
    assert r["paid_up"] is True
    assert r["days_remaining"] in (32, 33)
    assert r["max_devices"] == 5


@pytest.mark.asyncio
async def test_health_unhealthy_when_expired(fake_session, FakeResponseFixture):
    import datetime
    past = (datetime.datetime.now(datetime.UTC) -
            datetime.timedelta(days=5)).isoformat()
    fake_session.stub("POST", "/auth/v1/token",
                      FakeResponseFixture(json_data={"access_token": "t"}))
    fake_session.stub("GET", "/accounts/v1/accounts/me",
                      FakeResponseFixture(json_data={"expiry": past}))
    svc = Mullvad({"account_number": "1"*16}, fake_session)
    r = await svc.health()
    assert r["ok"] is False
    assert r["days_remaining"] <= 0


# ── devices ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_devices_returns_shaped_list(fake_session, FakeResponseFixture):
    fake_session.stub("POST", "/auth/v1/token",
                      FakeResponseFixture(json_data={"access_token": "t"}))
    fake_session.stub("GET", "/accounts/v1/devices",
                      FakeResponseFixture(json_data=[
                          {"name": "needed clam", "ipv4_address": "10.69.248.187/32",
                           "pubkey": "DvIqZi0EldLSoqa4SiwF2fQy", "created": "2025-10-07"},
                          {"name": "novel spider", "ipv4_address": "10.70.170.87/32",
                           "pubkey": "ixs2U/44XacGwQLxaFVVG1DW", "created": "2026-02-09"},
                      ]))
    svc = Mullvad({"account_number": "1"*16}, fake_session)
    r = await svc.devices()
    assert r["count"] == 2
    names = {d["name"] for d in r["devices"]}
    assert "novel spider" in names
    assert r["devices"][1]["ipv4"] == "10.70.170.87"
    # Cache: second call should return the same shape without re-fetching.
    r2 = await svc.devices()
    assert r2["count"] == 2


# ── routing check ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_routing_uses_gluetun_when_configured(fake_session, FakeResponseFixture):
    """If gluetun_url is set, the check should pull the public IP from gluetun's
    control API instead of an external service. Important for the offline case
    when ifconfig.me isn't reachable."""
    fake_session.stub("GET", "/v1/publicip/ip",
                      FakeResponseFixture(json_data={"public_ip": "146.70.171.133"}))
    fake_session.stub("GET", "/146.70.171.133/org",
                      FakeResponseFixture(status=200, text_data="AS9009 M247 Europe SRL"))
    svc = Mullvad({"account_number": "1"*16, "gluetun_url": "http://gluetun:8000"},
                  fake_session)
    r = await svc.check_routing()
    assert r["public_ip"] == "146.70.171.133"
    assert r["source"] == "gluetun"
    assert r["looks_mullvad"] is True   # M247 is a Mullvad partner ASN


@pytest.mark.asyncio
async def test_check_routing_detects_non_mullvad_ip(fake_session, FakeResponseFixture):
    """If the public IP comes back as a regular ISP, looks_mullvad must be False."""
    fake_session.stub("GET", "/v1/publicip/ip",
                      FakeResponseFixture(json_data={"public_ip": "1.2.3.4"}))
    fake_session.stub("GET", "/1.2.3.4/org",
                      FakeResponseFixture(status=200, text_data="AS7922 Comcast Cable"))
    svc = Mullvad({"account_number": "1"*16, "gluetun_url": "http://gluetun:8000"},
                  fake_session)
    r = await svc.check_routing()
    assert r["looks_mullvad"] is False


def test_tools_present():
    svc = Mullvad({"account_number": "1"*16}, None)
    names = {t.name for t in svc.tools()}
    assert names == {"mullvad_status", "mullvad_devices", "mullvad_check_routing"}
