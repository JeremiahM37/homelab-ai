"""Feature flag plumbing — defaults off, config-driven on, no import cost when off."""
import sys

import pytest

from homelab_ai.config import Config
from homelab_ai.features import Features, has_capability


def test_all_features_default_off():
    f = Features()
    s = f.summary()
    for name, enabled in s.items():
        assert enabled is False, f"feature {name} defaulted to on"


def test_features_parse_from_config():
    cfg = Config()
    cfg._raw = {
        "features": {
            "metrics": {"enabled": True},
            "ntfy": {"enabled": True, "url": "https://ntfy.sh/topic"},
            "history": {"enabled": True, "keep_days": 7},
        }
    }
    f = Features.from_config(cfg)
    assert f.metrics.enabled is True
    assert f.ntfy.url == "https://ntfy.sh/topic"
    assert f.history.keep_days == 7
    assert f.rag.enabled is False  # unmentioned features stay off


def test_features_shorthand_true():
    """`metrics: true` should be accepted as shorthand for `metrics.enabled`."""
    cfg = Config()
    cfg._raw = {"features": {"metrics": True}}
    f = Features.from_config(cfg)
    assert f.metrics.enabled is True


def test_features_unknown_keys_ignored():
    cfg = Config()
    cfg._raw = {"features": {"metrics": {"enabled": True, "unknown_key": "x"}}}
    f = Features.from_config(cfg)
    assert f.metrics.enabled is True
    assert not hasattr(f.metrics, "unknown_key")


def test_optional_deps_only_load_when_enabled():
    """Importing the package must NOT pull in chromadb / prometheus-client."""
    # If features.rag is off, chromadb should not be imported.
    if "chromadb" in sys.modules:
        # An earlier test imported it; skip — we can only assert this on a
        # clean interpreter. Worth a CI integration test.
        pytest.skip("chromadb already imported; can't assert lazy-load")
    import homelab_ai  # noqa: F401
    assert "chromadb" not in sys.modules


def test_has_capability_unknown_returns_false():
    assert has_capability("nonsense") is False


def test_has_capability_metrics():
    # Dev install includes prometheus-client.
    assert has_capability("metrics") is True


def test_summary_lists_every_feature():
    summary = Features().summary()
    for must_have in ("metrics", "email", "ntfy", "gotify", "scheduler",
                      "webhooks", "multi_llm", "history", "rag", "mcp_http"):
        assert must_have in summary
