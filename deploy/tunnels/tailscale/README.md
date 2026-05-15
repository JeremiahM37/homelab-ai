# Tailscale tunnel

Puts homelab-ai on your tailnet at `http://<your-machine>:9105`. Devices on
your tailnet can reach it; nothing is exposed to the public internet.

## 1 — Get an auth key

In the [Tailscale admin console](https://login.tailscale.com/admin/settings/keys), generate a reusable, ephemeral, tag-scoped auth key:

- Reusable: lets you redeploy without manual approval each time
- Ephemeral: container goes away → node de-registers
- Tag: `tag:homelab-ai` (recommended — set ACLs around it)

## 2 — Bring up the stack

```bash
cp .env.example .env
# edit .env to paste your auth key
docker compose up -d
```

## 3 — Hit it

From any other tailnet device:

```
http://homelab-ai:9105/app
```

…or use the Tailscale IP from `tailscale status`. With auth enabled on
homelab-ai (`auth.enabled: true`), the tailnet protection layer is your
first defence and the API key is the second.

## Files

- `docker-compose.yml` — runs tailscaled + homelab-ai side-by-side
- `.env.example` — TS_AUTHKEY + TS_HOSTNAME placeholders
