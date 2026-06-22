# Features

homelab-ai is **modular by design**. Every optional feature is off by default and only loaded when you enable it. A minimal install runs as a tight monitoring agent + AI surface; turn the dials in `config.yaml` to add what you need.

## Off-by-default principle

A feature that's off costs nothing — no extra disk space, no extra RAM, no extra dependencies imported, no extra routes registered. Concretely:

- **Code paths**: feature modules are imported lazily *inside* the route or task that uses them, never at startup.
- **Routes**: the optional FastAPI routers (`/api/rag`, `/api/webhooks`, `/api/history`, `/mcp`, `/metrics`) are only added to the app if their feature flag is on.
- **Dependencies**: heavy deps (chromadb, prometheus-client) live behind pip extras. Without the extra installed, `import homelab_ai` doesn't touch them.

The result: an install footprint that grows with what *you* turn on, not with what the project ships.

## Quick reference

| Feature | Flag | Extra dep | Adds |
|---------|------|-----------|------|
| Prometheus metrics | `features.metrics.enabled` | `pip install homelab-ai[metrics]` | `/metrics` route |
| Email notifier (SMTP) | `features.email.enabled` | — | extra notifier backend |
| ntfy notifier | `features.ntfy.enabled` | — | extra notifier backend |
| Gotify notifier | `features.gotify.enabled` | — | extra notifier backend |
| Cron scheduler | `features.scheduler.enabled` | `pip install homelab-ai[scheduler]` | scheduled tool calls |
| Inbound webhooks | `features.webhooks.enabled` | — | `/api/webhooks/{name}` |
| Multi-LLM router | `features.multi_llm.enabled` | — | small + smart on different backends |
| Run history | `features.history.enabled` | — | SQLite log + `/api/history/*` |
| Document RAG | `features.rag.enabled` | `pip install homelab-ai[rag]` | `/api/rag/*` — hybrid (dense + BM25) search, optional LLM rerank, incremental indexing, visibility tiers |
| MCP HTTP server | `features.mcp_http.enabled` | — | `/mcp` JSON-RPC endpoint |
| Automation rules | `features.automations.enabled` | — | HA-style when-X-then-Y over Findings |
| Anomaly detection | `features.anomalies.enabled` | — | hour-of-day z-score outlier flagging (also requires `anomaly_detector` in `agent.modules`) |
| Web config editor | `features.config_editor.enabled` | — | `/api/config/*` for the PWA Config tab |

## Example: opting into a few features

```yaml
features:
  metrics:
    enabled: true        # /metrics for Grafana

  ntfy:
    enabled: true
    url: https://ntfy.sh/my-homelab-topic
    priority: high

  scheduler:
    enabled: true
    schedules:
      - name: morning_briefing
        cron: "0 7 * * *"
        tool: sonarr_calendar
        args: {days: 1}
        notify: discord

  webhooks:
    enabled: true
    receivers:
      grafana_alert:
        secret: ${WEBHOOK_GRAFANA_SECRET}
        tool: restart_service
        args:
          service: "{{service}}"      # rendered from POST body

  history:
    enabled: true
    keep_days: 30

  multi_llm:
    enabled: true
    small_backend: ollama
    small_url: http://localhost:11434
    small_model: qwen3.5:4b
    smart_backend: openai_compat
    smart_url: https://api.openai.com/v1
    smart_api_key: ${OPENAI_API_KEY}
    smart_model: gpt-4o-mini
    track_calls: true
```

Then install just the extras you need:

```bash
pip install homelab-ai[metrics,scheduler]
```

Or everything:

```bash
pip install homelab-ai[all]
```

## Verifying a feature is off (zero-cost check)

```python
from homelab_ai.config import load_config
from homelab_ai.features import Features

cfg = load_config("config.yaml")
print(Features.from_config(cfg).summary())
# {'metrics': False, 'email': False, 'ntfy': False, ...}
```

If everything reports False, no optional module has been imported.

## Adding your own feature

If you want a new toggle of your own:

1. Add a `@dataclass MyFeature` block in `homelab_ai/features.py` with `enabled: bool = False`.
2. Add it to `Features` and `summary()`.
3. Check `features.my_feature.enabled` wherever it gates code.
4. Keep imports of heavy deps lazy — inside the function that uses them.

The CONTRIBUTING checklist requires this for any addition that adds a runtime cost.
