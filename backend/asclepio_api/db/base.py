"""Engine/sessão assíncronos (SQLite por padrão, Postgres via DATABASE_URL)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():  # type: ignore[no-untyped-def]
    global _engine, _session_factory
    if _engine is None:
        s = get_settings()
        url = s.database_url
        if url.startswith("sqlite"):
            db_path = url.split("///")[-1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(
            url, echo=False, future=True, pool_pre_ping=not url.startswith("sqlite")
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


async def init_db() -> None:
    from . import models  # noqa: F401 — registra os modelos

    engine = get_engine()
    async with engine.begin() as conn:
        if str(engine.url).startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_columns)


def _ensure_columns(sync_conn) -> None:  # type: ignore[no-untyped-def]
    """Migração leve: adiciona colunas novas a tabelas já existentes (bancos criados por versões anteriores)."""
    from sqlalchemy import inspect, text

    insp = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ctype = col.type.compile(dialect=sync_conn.dialect)
            default = ""
            if (
                col.default is not None
                and getattr(col.default, "arg", None) is not None
                and not callable(col.default.arg)
            ):
                arg = col.default.arg
                if isinstance(arg, bool):
                    is_pg = sync_conn.dialect.name == "postgresql"
                    default = f" DEFAULT {('TRUE' if arg else 'FALSE') if is_pg else ('1' if arg else '0')}"
                else:
                    default = f" DEFAULT {arg!r}"
            elif col.type.__class__.__name__ == "JSON":
                default = " DEFAULT '[]'"
            sync_conn.execute(
                text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ctype}{default}')
            )


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
