"""FastAPI application for twag web interface."""

import html
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import get_database_path
from ..db import init_db
from .routes import context, prompts, reactions, tweets

# Paths
TEMPLATES_DIR = Path(__file__).parent / "templates"
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Twag",
        description="Twitter aggregator web interface",
        version="0.1.0",
    )

    app.state.db_path = get_database_path()

    # CORS: restrict to localhost origins
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize database
    init_db(app.state.db_path)

    # Set up templates (unescape filter used in tests)
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env.filters["unescape"] = lambda s: html.unescape(s) if s else s
    app.state.templates = templates

    # Include API routers
    app.include_router(tweets.router, prefix="/api")
    app.include_router(reactions.router, prefix="/api")
    app.include_router(prompts.router, prefix="/api")
    app.include_router(context.router, prefix="/api")

    # In dev mode (TWAG_DEV=1), skip SPA serving — Vite dev server handles frontend
    dev_mode = os.environ.get("TWAG_DEV") == "1"

    if not dev_mode and (FRONTEND_DIST / "index.html").exists():
        # Production: serve built SPA
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="assets",
        )

        @app.get("/{full_path:path}", response_class=HTMLResponse)
        async def spa_catch_all(request: Request, full_path: str):
            """Serve SPA index.html for all non-API routes."""
            if full_path:
                resolved = (FRONTEND_DIST / full_path).resolve()
                if resolved.is_relative_to(FRONTEND_DIST) and resolved.is_file():
                    return FileResponse(resolved)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
