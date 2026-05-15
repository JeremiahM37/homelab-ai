# Remote-access tunnel templates

By default homelab-ai listens on `0.0.0.0:9105` — fine for a LAN. To reach it from outside your network, put it behind a tunnel.

Two ready-to-use templates:

| Tunnel | When to use | Effort |
|--------|-------------|--------|
| **Tailscale** | You already use Tailscale, or you want zero-trust access without exposing anything publicly. | low |
| **Cloudflare Tunnel** | You want a public hostname (`homelab-ai.yourdomain.com`) without opening ports. | medium |

See `tailscale/` and `cloudflared/` for the docker-compose snippets and config.
