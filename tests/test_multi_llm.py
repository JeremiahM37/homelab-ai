"""Multi-LLM router — small/smart split."""
import pytest

from homelab_ai.features import MultiLLMFeature
from homelab_ai.llm.multi import MultiLLMRouter


def _feat():
    return MultiLLMFeature(
        enabled=True,
        small_backend="ollama", small_url="http://small:11434", small_model="phi",
        smart_backend="openai_compat", smart_url="https://api.openai.com",
        smart_api_key="sk-x", smart_model="gpt-4o-mini",
        track_calls=True,
    )


def test_router_small_returns_ollama():
    r = MultiLLMRouter(_feat(), http=None)
    client, model = r.client_for("small")
    assert client.__class__.__name__ == "OllamaClient"
    assert model == "phi"


def test_router_smart_returns_openai():
    r = MultiLLMRouter(_feat(), http=None)
    client, model = r.client_for("smart")
    assert client.__class__.__name__ == "OpenAICompatClient"
    assert model == "gpt-4o-mini"


def test_router_unknown_tier_falls_back_to_small():
    r = MultiLLMRouter(_feat(), http=None)
    client, model = r.client_for("medium")
    assert model == "phi"


def test_router_tracks_call_counts():
    r = MultiLLMRouter(_feat(), http=None)
    r.client_for("small")
    r.client_for("small")
    r.client_for("smart")
    assert r.call_counts() == {"small": 2, "smart": 1}


def test_router_rejects_unknown_backend():
    f = _feat()
    f.small_backend = "magic"
    with pytest.raises(ValueError):
        MultiLLMRouter(f, http=None)
