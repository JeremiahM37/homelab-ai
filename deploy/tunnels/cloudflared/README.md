# Cloudflare Tunnel

Exposes homelab-ai at `https://<your-hostname>.yourdomain.com` without
opening any ports — Cloudflare connects outbound to the tunnel, and your
homelab-ai stays on the LAN.

## 1 — Create the tunnel

```bash
cloudflared tunnel login                          # browser auth
cloudflared tunnel create homelab-ai              # writes credentials to ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns homelab-ai homelab-ai.yourdomain.com
```

Copy the printed UUID + path to the credentials file.

## 2 — Wire it up

```bash
cp .env.example .env                              # paste UUID + token
# edit cloudflared/config.yml — replace TUNNEL_UUID and hostname
docker compose up -d
```

## 3 — Strongly recommended

Turn on **Cloudflare Access** for the hostname:
- Dashboard → Zero Trust → Access → Applications → Add an application
- Restrict to your email / IdP / device posture

That way only authenticated users hit homelab-ai's auth layer.

## Files

- `docker-compose.yml` — cloudflared sidecar + homelab-ai
- `config.yml` — tunnel ingress rules (edit the hostname placeholder)
- `.env.example` — UUID + token placeholders
