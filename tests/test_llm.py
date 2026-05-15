"""LLM backend selection and message-shape normalisation."""
from unittest.mock import AsyncMock

import pytest

from homelab_ai.config import Config
from homelab_ai.llm import get_client, get_model
from homelab_ai.llm.openai_compat import (
    OpenAICompatClient,
    _normalize_messages,
    _normalize_response,
)


def test_get_client_auto_picks_ollama_for_11434():
    cfg = Config()
    cfg._raw = {"llm": {"backend": "auto", "url": "http://localhost:11434"}}
    client = get_client(cfg, None)
    assert client.__class__.__name__ == "OllamaClient"


def test_get_client_auto_picks_openai_for_v1():
    cfg = Config()
    cfg._raw = {"llm": {"backend": "auto", "url": "http://localhost:8000/v1"}}
    client = get_client(cfg, None)
    assert client.__class__.__name__ == "OpenAICompatClient"


def test_get_client_explicit_openai():
    cfg = Config()
    cfg._raw = {"llm": {"backend": "openai_compat",
                        "url": "http://localhost:11434", "api_key": "sk-x"}}
    client = get_client(cfg, None)
    assert isinstance(client, OpenAICompatClient)
    # URL should have been normalized to include /v1.
    assert client.url.endswith("/v1")


def test_get_client_unknown_backend_raises():
    cfg = Config()
    cfg._raw = {"llm": {"backend": "nope", "url": "http://x"}}
    with pytest.raises(ValueError):
        get_client(cfg, None)


def test_get_model_prefers_llm_block():
    cfg = Config()
    cfg._raw = {
        "llm": {"small_model": "phi:mini", "smart_model": "llama:big"},
        "ollama": {"small_model": "old", "smart_model": "old"},
    }
    assert get_model(cfg, "small") == "phi:mini"
    assert get_model(cfg, "smart") == "llama:big"


def test_get_model_falls_back_to_ollama():
    """Legacy v0.2 configs that only set the `ollama:` block should still work."""
    cfg = Config()
    cfg._raw = {"ollama": {"small_model": "legacy-small"}}
    assert get_model(cfg, "small") == "legacy-small"


def test_openai_compat_url_normalizes_v1():
    c = OpenAICompatClient("http://x:8000", http=None)
    assert c.url == "http://x:8000/v1"
    c2 = OpenAICompatClient("http://x:8000/v1", http=None)
    assert c2.url == "http://x:8000/v1"


def test_openai_compat_headers_include_bearer():
    c = OpenAICompatClient("http://x", http=None, api_key="sk-abc")
    h = c._headers()
    assert h["Authorization"] == "Bearer sk-abc"


def test_openai_compat_headers_omit_bearer_when_unset():
    c = OpenAICompatClient("http://x", http=None)
    assert "Authorization" not in c._headers()


def test_normalize_messages_backfills_tool_call_id():
    msgs = _normalize_messages([
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "{}"},   # no tool_call_id
    ])
    assert msgs[1]["tool_call_id"]


def test_normalize_response_squashes_to_ollama_shape():
    data = {"choices": [{"message": {"role": "assistant", "content": "hi", "tool_calls": []}}]}
    r = _normalize_response(data)
    assert r["message"]["content"] == "hi"
    assert r["message"]["tool_calls"] == []


def test_normalize_response_handles_empty_choices():
    r = _normalize_response({"choices": []})
    assert r["message"]["content"] == ""
