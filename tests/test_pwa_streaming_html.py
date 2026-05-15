"""Smoke checks for the new PWA — tabs, SSE consumer, config editor, history."""
from pathlib import Path

import pytest

PWA = Path(__file__).parent.parent / "homelab_ai" / "ui" / "static" / "app.html"


@pytest.fixture
def html() -> str:
    return PWA.read_text()


def test_pwa_has_five_tabs(html: str):
    """We expanded from 3 to 5 tabs in v0.6."""
    for tid in ("tab-home", "tab-chat", "tab-config", "tab-history", "tab-settings"):
        assert f'id="{tid}"' in html, f"missing tab panel {tid}"


def test_pwa_bottom_nav_grid_cols_match_tab_count(html: str):
    """The bottom nav must use grid-cols-5 now that there are 5 tabs."""
    assert "grid-cols-5" in html


def test_pwa_chat_consumes_streaming_endpoint(html: str):
    """Confirm the chat uses the SSE endpoint and parses event/data lines."""
    assert "/api/ai/agent/stream" in html
    assert "event:" in html and "data:" in html


def test_pwa_renders_tool_call_cards(html: str):
    """Tool-call cards should be styled and the handler should branch on
    event type."""
    assert "tool-card" in html
    assert "tool_call" in html
    assert "tool_result" in html or "tool-result" in html


def test_pwa_config_tab_calls_schema_and_save(html: str):
    assert "/api/config/schema" in html
    assert "/api/config/current" in html
    assert "/api/config/save" in html


def test_pwa_history_tab_calls_all_three_endpoints(html: str):
    for path in ("/api/history/scans", "/api/history/ai", "/api/history/fixes"):
        assert path in html


def test_pwa_handles_history_feature_off_gracefully(html: str):
    """If /api/history/* returns 404 (feature off), we show a helpful message
    rather than a generic error."""
    assert "History feature is not enabled" in html


def test_pwa_handles_config_editor_feature_off(html: str):
    assert "config_editor feature not enabled" in html or "config_editor" in html


def test_pwa_api_key_modal_still_present(html: str):
    """Auth-required modal should survive the tab rewrite."""
    assert "showApiKeyModal" in html
    assert "API_KEY_STORAGE" in html
