"""homelab-ai status — health probe CLI."""
import sys
from unittest.mock import patch

import pytest

from homelab_ai.__main__ import _cmd_status


class _Args:
    def __init__(self, url=None, timeout=3.0, config=None):
        self.url = url
        self.timeout = timeout
        from pathlib import Path
        self.config = config or Path("/nonexistent.yaml")


@pytest.fixture
def fake_urlopen():
    """Patch urllib.request.urlopen used inside _cmd_status."""
    import io
    import urllib.request
    with patch.object(urllib.request, "urlopen") as m:
        yield m


def test_status_up_returns_0_when_health_ok(fake_urlopen, capsys):
    import io
    fake_urlopen.return_value.__enter__.return_value.read.return_value = b'{"ok": true, "version": "0.6.0"}'
    rc = _cmd_status(_Args(url="http://localhost:9105"))
    assert rc == 0
    captured = capsys.readouterr()
    assert "UP" in captured.out
    assert "0.6.0" in captured.out


def test_status_down_returns_1_on_urlerror(fake_urlopen, capsys):
    import urllib.error
    fake_urlopen.side_effect = urllib.error.URLError("connection refused")
    rc = _cmd_status(_Args(url="http://localhost:9999"))
    assert rc == 1
    captured = capsys.readouterr()
    assert "DOWN" in captured.err
    assert "connection refused" in captured.err


def test_status_degraded_returns_1_when_health_ok_false(fake_urlopen, capsys):
    fake_urlopen.return_value.__enter__.return_value.read.return_value = b'{"ok": false}'
    rc = _cmd_status(_Args(url="http://localhost:9105"))
    assert rc == 1
    captured = capsys.readouterr()
    assert "DEGRADED" in captured.err


def test_status_uses_config_host_port_when_no_url(fake_urlopen, tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("server:\n  host: 0.0.0.0\n  port: 9876\n")
    fake_urlopen.return_value.__enter__.return_value.read.return_value = b'{"ok": true, "version": "x"}'
    rc = _cmd_status(_Args(config=cfg_file))
    assert rc == 0
    # 0.0.0.0 should be rewritten to 127.0.0.1 for the probe.
    args, kwargs = fake_urlopen.call_args
    assert "127.0.0.1:9876" in args[0]
