"""Logging estruturado com structlog: request_id/trace_id em todas as linhas, JSON em produção.

Por que structlog? Logs legíveis em dev (console colorido) e *machine-readable* em prod
(JSON → fácil de enviar para Loki/ELK/Datadog), com contexto automático (request_id,
usuário, rota) — requisito do desafio: "logging detalhado para rastreamento e auditoria".
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def _add_request_id(_, __, event_dict):  # type: ignore[no-untyped-def]
    event_dict.setdefault("request_id", request_id_ctx.get())
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO)
    )
    for noisy in ("httpx", "httpcore", "chromadb", "uvicorn.access", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):  # type: ignore[no-untyped-def]
    return structlog.get_logger(name) if name else structlog.get_logger()
