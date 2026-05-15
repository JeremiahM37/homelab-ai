# Migration guide

You probably already have *something* watching your homelab — a bespoke Python script with cron, an n8n workflow, Uptime Kuma + a Discord webhook. This is how to replace that with homelab-ai without losing functionality.

## TL;DR

1. List what you currently monitor and what each thing does.
2. For each, find (or write) the homelab-ai equivalent: a service plugin, an agent module, or a custom tool.
3. Run homelab-ai *alongside* your existing setup on a different port.
4. Compare for a week.
5. Cut over.

Do **not** delete the old setup until you've watched homelab-ai react to at least one real failure.

## Step 1 — Inventory

Make a list. For each item:

| What | Trigger | Action |
|------|---------|--------|
| Sonarr unreachable | HTTP 5xx on /system/status | Discord ping |
| qBittorrent crashed | Container exited | `docker restart qbittorrent` |
| Disk >90% | `df` output | Email + cleanup script |
| New PR on my repo | `gh api` poll | Mobile push |

## Step 2 — Map to homelab-ai

Each entry maps to one of three things:

### A built-in service plugin

If the target is a popular self-hosted app, there's probably already a plugin. Check `homelab_ai/services/`. Wire it up by adding a block to `config.yaml`:

```yaml
services:
  sonarr:
    url: http://sonarr:8989
    api_key: ${SONARR_API_KEY}
```

The agent's `service_health` module will start hitting `health()` on every scan. Tier-1 will call `restart()` on failure.

### A built-in agent module

If your trigger isn't tied to a specific service — e.g. "disk full" or "this container is using 50% RAM" — it probably lives in `homelab_ai/agent/modules/`:

- `service_health` — calls `health()` on every loaded service
- `disk_watcher` — current % usage thresholds
- `disk_forecast` — 7-day trend, days-to-full projection
- `container_doctor` — Docker state (exited/restarting/crash-looping)
- `container_resources` — CPU/RAM outlier detection with consecutive-scan streaks
- `vpn_watchdog` — public-IP probe for VPN-backed containers
- `import_watchdog` — stuck items in *arr import queues

Enable them in `config.yaml`:

```yaml
agent:
  modules:
    - service_health
    - disk_forecast
    - container_doctor
    - vpn_watchdog
```

### A user plugin

For everything else, write a plugin file. Two flavours:

- **Service plugin** — see [adding-services.md](adding-services.md). Drop a `.py` file into `~/.config/homelab-ai/services/`.
- **Agent module** — see [adding-tools.md](adding-tools.md). Drop a `.py` file into `~/.config/homelab-ai/agent_modules/`.
- **Custom shell command** — wire a `command:` service plugin in `config.yaml`:

  ```yaml
  services:
    command:
      commands:
        - name: poll_my_repo
          description: Check for new PRs on the active branch.
          shell: "gh pr list --json number,title"
  ```

  This becomes an AI tool the agent can call.

## Step 3 — Run side-by-side

Put homelab-ai on a port that doesn't conflict with your existing setup. In `config.yaml`:

```yaml
server:
  port: 9108   # whatever's free
```

In `docker-compose.yml`:

```yaml
services:
  homelab-ai:
    image: ghcr.io/JeremiahM37/homelab-ai:latest
    ports:
      - "9108:9105"   # external:internal
```

The agent's failure-memory SQLite is local to homelab-ai's data dir, so your old monitor and the new one won't interfere.

## Step 4 — Compare

Watch both for a week. Useful comparisons:

- **Coverage**: does the old monitor catch failures homelab-ai missed?
- **Noise**: does homelab-ai dedupe better / worse than the old setup?
- **Repair**: does Tier-1/2/3 fix things you used to fix manually?

If homelab-ai is missing a check, write a module for it. If it's noisy, tune `agent.notify.rate_limit_per_hour` or extend the failure-memory cooldown.

## Step 5 — Cut over

Once homelab-ai has handled at least one production failure correctly without you intervening:

1. Disable the old systemd timer / cron job / n8n workflow.
2. Move homelab-ai onto the primary port (or behind your reverse proxy).
3. Keep the old code around for a release cycle in case you need to roll back.
4. Delete the old code.

## Common patterns

### "I want Discord alerts for X"

Set `agent.notify.discord_webhook` and X will be alerted on as long as it's a `Finding` produced by some module. Default dedup is 1 hour per fingerprint, 20 alerts/hour cap.

### "I want a tool the AI can call that runs a custom thing"

Drop a service plugin under `~/.config/homelab-ai/services/`. Any `tools()` it returns become AI-callable and MCP-exposed automatically.

### "I want to wire homelab-ai into Claude Desktop"

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (mac) or the equivalent on your OS:

```json
{
  "mcpServers": {
    "homelab-ai": {
      "command": "homelab-ai",
      "args": ["--config", "/etc/homelab-ai/config.yaml", "mcp-server"]
    }
  }
}
```

### "My old monitor used cron, not a daemon"

Run `homelab-ai --config /etc/homelab-ai/config.yaml scan` from cron. The scan runs once and exits. State persists in `./data/agent.db` so dedup works across runs.

### "I have a complex multi-step automation in n8n"

Two options:

1. Keep n8n for the orchestration and have homelab-ai's tools be n8n HTTP-call targets.
2. Replace the workflow with a script + `command:` plugin so the AI can trigger it.

Choice depends on whether the workflow needs visual editing or just needs to be callable.
