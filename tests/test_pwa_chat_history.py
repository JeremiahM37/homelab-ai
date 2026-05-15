"""PWA chat history persistence — HTML smoke checks."""
from pathlib import Path

import pytest

PWA = Path(__file__).parent.parent / "homelab_ai" / "ui" / "static" / "app.html"


@pytest.fixture
def html() -> str:
    return PWA.read_text()


def test_chat_uses_localstorage_key(html: str):
    assert "homelab_ai_chat_history" in html
    assert "CHAT_HISTORY_KEY" in html


def test_chat_has_load_save_clear_handlers(html: str):
    for fn in ("loadChatHistory", "saveChatTurn", "clearChat"):
        assert f"function {fn}" in html


def test_chat_clear_button_in_input_row(html: str):
    assert "onclick=\"clearChat()\"" in html


def test_chat_history_bounded_to_50_turns(html: str):
    assert "CHAT_MAX_TURNS" in html
    assert "50" in html


def test_chat_history_loaded_on_boot(html: str):
    """The boot block should call loadChatHistory()."""
    # Look for the boot section (last loadHome() call near end of file).
    assert "loadChatHistory()" in html


def test_chat_save_called_on_completion_and_error(html: str):
    """Both the success path and the error path persist the turn."""
    assert html.count("saveChatTurn(turn)") >= 2
