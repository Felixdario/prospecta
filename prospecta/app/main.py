"""Aplicação web: API + painel estático + worker de pesquisas.

Execute com:  python -m app            (usa HOST/PORT do .env)
ou           uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from .api import RateLimiter, routes
from .config import PROJECT_ROOT, Config, load_config
from .db import Database
from .jobs import Worker
from .repository import Repo
from .services import Services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("prospecta")


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def build_services(config: Config) -> Services:
    db = Database(config.database_path)
    db.init()
    return Services(Repo(db), config)


def create_app(config: Config | None = None, services: Services | None = None, start_worker: bool = True) -> Starlette:
    config = config or load_config()
    services = services or build_services(config)
    worker = Worker(services)

    @asynccontextmanager
    async def lifespan(app):
        if not config.admin_token:
            log.warning("ADMIN_TOKEN não definido: rode 'python -m app.cli init' para gerar um.")
        if start_worker:
            worker.start()
        services.repo.prune_audit()
        yield
        if start_worker:
            worker.stop()

    app = Starlette(
        routes=[*routes(), Mount("/", StaticFiles(directory=PROJECT_ROOT / "static", html=True), name="static")],
        middleware=[Middleware(SecurityHeaders)],
        lifespan=lifespan,
    )
    app.state.services = services
    app.state.worker = worker
    app.state.limiter = RateLimiter(config.api_rate_limit_per_minute)
    return app


def _lazy_app():
    return create_app()


class _LazyASGI:
    """Permite `uvicorn app.main:app` sem criar o banco no momento do import (útil nos testes)."""

    def __init__(self):
        self._app = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = _lazy_app()
        await self._app(scope, receive, send)


app = _LazyASGI()
