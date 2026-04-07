"""Async SQLAlchemy engine + session factory.

Supports both PostgreSQL (asyncpg) and SQLite (aiosqlite) for dev fallback.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nexus.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite doesn't support pool_size or pool_pre_ping
_engine_kwargs = {"echo": False}
if not _is_sqlite:
    _engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async DB session with auto-commit/rollback."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
