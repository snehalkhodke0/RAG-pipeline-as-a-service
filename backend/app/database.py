"""Async SQLAlchemy engine, session factory, and declarative base."""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Dict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# asyncpg connections are bound to whichever event loop was running when they were
# created. Under pytest-asyncio, each test (or each session, depending on scope) can
# run on its own loop, so a connection pooled from one loop and handed to another
# blows up with "attached to a different loop". NullPool sidesteps this entirely by
# never reusing a connection across checkouts - every checkout opens fresh and closes
# immediately after. Production keeps normal pooling; only the test process (which
# sets TESTING=1 in tests/conftest.py) pays the extra connect cost.
_pool_kwargs: Dict[str, Any] = (
    {"poolclass": NullPool} if os.environ.get("TESTING") == "1" else {"pool_size": 5, "max_overflow": 5}
)

# Managed Postgres providers (Supabase, Neon) front their pooled connection strings
# with PgBouncer in transaction mode, which does not support asyncpg's server-side
# prepared statement cache (a query's prepared statement can silently end up on a
# different underlying connection mid-session). Disabling it makes the engine safe to
# point at either a transaction-mode pooler or a direct connection with no downside
# beyond skipping query-plan caching.
_connect_args: Dict[str, Any] = {"statement_cache_size": 0} if "asyncpg" in settings.DATABASE_URL else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=_connect_args,
    **_pool_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
