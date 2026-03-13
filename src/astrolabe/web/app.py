"""FastAPI application factory for astrolabe web UI."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from astrolabe.web.state import AppState

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize AppState on startup."""
    logger.info("Starting astrolabe web UI...")
    app.state.astrolabe = AppState.create()
    logger.info(
        "Loaded %d documents from index",
        len(app.state.astrolabe.index.documents),
    )
    yield


def get_state(request: Request) -> AppState:
    """Get AppState from request."""
    return request.app.state.astrolabe  # type: ignore[no-any-return]


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(title="Astrolabe", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    from astrolabe import __version__

    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    # Global template variables available in all templates
    templates.env.globals["version"] = __version__
    templates.env.globals["search_query"] = ""

    # Store templates on app for route access
    app.state.templates = templates

    # Register routes
    from astrolabe.web.routes_api import router as api_router
    from astrolabe.web.routes_pages import router as pages_router

    app.include_router(pages_router)
    app.include_router(api_router, prefix="/api")

    return app


def main(host: str = "127.0.0.1", port: int = 8420) -> None:
    """Run the web server."""
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=host, port=port)
