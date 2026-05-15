"""FastAPI application factory + uvicorn entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from homelab_ai.agent.loop import run_forever
from homelab_ai.config import Config
from homelab_ai.services import load_services

logger = logging.getLogger("homelab_ai.api")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    cfg: Config = app.state.cfg
    app.state.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    app.state.services = load_services(cfg, app.state.http)
    if cfg.agent.enabled:
        app.state.agent_task = asyncio.create_task(run_forever(cfg))
    else:
        app.state.agent_task = None
    try:
        yield
    finally:
        if app.state.agent_task:
            app.state.agent_task.cancel()
        await app.state.http.close()


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(
        title="homelab-ai",
        description="Self-hosted AI orchestrator for your homelab.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.cfg = cfg
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.server.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    from homelab_ai.api.routers import agent, ai, services, settings
    app.include_router(agent.router)
    app.include_router(ai.router)
    app.include_router(services.router)
    app.include_router(settings.router)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": "0.1.0"}

    @app.get("/api/overview")
    async def overview():
        out = {}
        for name, svc in app.state.services.items():
            try:
                out[name] = await svc.health()
            except Exception as e:
                out[name] = {"ok": False, "error": str(e)[:200]}
        return out

    # Mobile PWA
    static_dir = Path(__file__).parent.parent / "ui" / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/app")
        async def mobile_app():
            return FileResponse(static_dir / "app.html")

        @app.get("/")
        async def root():
            return HTMLResponse(
                "<h1>homelab-ai</h1>"
                "<p>Mobile app: <a href='/app'>/app</a> · "
                "API docs: <a href='/docs'>/docs</a></p>"
            )

    return app


def serve(cfg: Config) -> int:
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, log_level="info")
    return 0
