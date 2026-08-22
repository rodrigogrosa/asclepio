"""Aplicação FastAPI do Asclépio.

Camadas de proteção (de fora para dentro):
request-id → headers de segurança → limite de tamanho do corpo → CORS → rate limit → auth (JWT) → RBAC → handlers.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import get_settings
from .core.logging import configure_logging, get_logger, new_request_id, request_id_ctx
from .db.base import dispose_db, init_db, session_factory
from .db.seed import run_seed
from .main_limiter import limiter
from .routers import (
    alerts,
    assistant,
    audit,
    auth,
    catalog,
    dashboard,
    knowledge,
    model,
    patients,
    public,
    system,
    users,
    workflows,
)
from .services.knowledge import get_knowledge_service
from .services.model_info import load_persisted_model
from .services.workflow import get_workflow_runtime

log = get_logger("app")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gera/propaga X-Request-ID, mede latência e loga cada requisição."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or new_request_id()
        token = request_id_ctx.set(rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        ms = int((time.perf_counter() - t0) * 1000)
        if not request.url.path.endswith(("/health", "/metrics")):
            log.info(
                "http",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=ms,
                request_id=rid,
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        s = get_settings()
        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl and int(cl) > s.max_request_body_bytes:
                return JSONResponse(
                    {"detail": "Corpo da requisição excede o limite permitido"}, status_code=413
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        if s.is_prod:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    s = get_settings()
    configure_logging(s.log_level, s.log_format)
    log.info(
        "iniciando",
        app=s.app_name,
        env=s.app_env,
        llm_provider=s.llm_provider,
        llm_model=s.llm_model,
        embeddings=s.embeddings_provider,
    )
    await init_db()
    async with session_factory()() as session:
        if s.seed_on_startup:
            await run_seed(session)
        await load_persisted_model(session)
    try:
        res = await run_in_threadpool(get_knowledge_service().ensure_index)
        log.info(
            "base de conhecimento pronta", **{k: v for k, v in res.items() if k != "reindexed"}
        )
    except Exception as exc:
        log.error(
            "falha ao indexar base de conhecimento (o assistente responderá sem RAG até a reindexação)",
            error=str(exc),
        )
    await get_workflow_runtime().start()
    log.info("pronto", docs="/docs")
    yield
    await get_workflow_runtime().stop()
    await dispose_db()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Asclépio API",
        version=s.app_version,
        description="Assistente clínico inteligente — LLM fine-tunada + LangChain/LangGraph, com guardrails, RAG com fontes, anonimização e auditoria. Tech Challenge FIAP · Fase 3.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
        # Permite detail estruturado ({"detail": "...", "code": "..."}) sem aninhar em {"detail": {...}}
        body = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        return JSONResponse(
            body, status_code=exc.status_code, headers=getattr(exc, "headers", None)
        )

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    if s.enable_metrics:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(excluded_handlers=["/metrics", "/health"]).instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )

    api = s.api_prefix
    for r in (
        auth.router,
        users.router,
        catalog.router,
        public.router,
        dashboard.router,
        patients.router,
        assistant.router,
        workflows.router,
        alerts.router,
        knowledge.router,
        model.router,
        audit.router,
    ):
        app.include_router(r, prefix=api)
    app.include_router(system.router, prefix=api)
    app.include_router(system.router)  # /health também na raiz (healthcheck do Docker)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"app": s.app_name, "docs": "/docs", "api": api, "health": "/health"}

    return app


app = create_app()
