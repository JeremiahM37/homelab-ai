"""Console entry point: `homelab-ai run` / `homelab-ai verify` / `homelab-ai scan`."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="homelab-ai", description="homelab-ai CLI")
    parser.add_argument(
        "-c", "--config", type=Path, default=Path("config.yaml"),
        help="Path to config.yaml (default: ./config.yaml)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Start the HTTP server + agent loop")
    p_run.add_argument("--host", default=None)
    p_run.add_argument("--port", type=int, default=None)

    sub.add_parser("scan", help="Run a single agent scan and exit")
    sub.add_parser("verify", help="Run the verification suite")
    sub.add_parser("mcp-server", help="Run the MCP stdio server (for Claude Desktop, Cursor, etc.)")
    p_init = sub.add_parser("init", help="Generate a config.yaml interactively")
    p_init.add_argument("--yes", action="store_true", help="Non-interactive (use defaults)")
    sub.add_parser("demo", help="Boot with fake services for a no-setup tour")
    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "version":
        from homelab_ai import __version__
        print(__version__)
        return 0

    if args.cmd == "run":
        from homelab_ai.api.main import serve
        from homelab_ai.config import load_config
        cfg = load_config(args.config)
        if args.host:
            cfg.server.host = args.host
        if args.port:
            cfg.server.port = args.port
        return serve(cfg)

    if args.cmd == "scan":
        from homelab_ai.agent.loop import scan_once
        from homelab_ai.config import load_config
        cfg = load_config(args.config)
        return asyncio.run(scan_once(cfg))

    if args.cmd == "verify":
        from homelab_ai.config import load_config
        from homelab_ai.verify.runner import run_all
        cfg = load_config(args.config)
        return run_all(cfg)

    if args.cmd == "mcp-server":
        from homelab_ai.config import load_config
        from homelab_ai.mcp.server import run_mcp_server
        cfg = load_config(args.config)
        return run_mcp_server(cfg)

    if args.cmd == "init":
        from homelab_ai.init_wizard import run_init
        return run_init(args.config, yes=args.yes)

    if args.cmd == "demo":
        from homelab_ai.demo import run_demo
        return run_demo()

    return 2


if __name__ == "__main__":
    sys.exit(main())
