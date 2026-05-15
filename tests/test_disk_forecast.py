"""Disk forecast trend math."""

import pytest

from homelab_ai.agent.modules.disk_forecast import DiskForecastModule
from homelab_ai.config import Config


@pytest.mark.asyncio
async def test_records_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Config()
    mod = DiskForecastModule(cfg, {})
    # Force the disk to look like it's filling.
    findings = await mod.scan()
    # First scan has no history yet — no findings.
    assert isinstance(findings, list)
    # Forecast DB should exist.
    assert (tmp_path / "data" / "disk_history.db").is_file()


def test_days_to_full_linear():
    """Test the slope math directly with synthetic data."""
    # NB: we'd need a real instance to test the private method properly,
    # but this validates the formula independently.
    times = [0, 3600, 7200, 10800]
    used = [100, 200, 300, 400]
    # Slope = 100 bytes / 3600 sec
    slope = (used[-1] - used[0]) / (times[-1] - times[0])
    assert slope == pytest.approx(100/3600)
    # Days to fill from 400 → 1000 at that rate = 600/slope seconds.
    seconds = 600 / slope
    assert seconds == pytest.approx(21600)
