"""Shared fixtures for the integration test suite.

These tests need a live Postgres + pgvector instance (the same one docker-compose
brings up for local dev). By default they point at that same `rag` database and
truncate all tables before every test for isolation; set TEST_DATABASE_URL to point
at a separate database instead if you'd rather not share it with dev data.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import AsyncGenerator

if sys.platform == "win32":
    # asyncpg's overlapped I/O has a known teardown incompatibility with Windows'
    # default ProactorEventLoop (surfaces as a spurious
    # "AttributeError: 'NoneType' object has no attribute 'send'" during connection
    # close). The Selector loop doesn't have this issue and is what asyncpg
    # recommends on Windows for exactly this reason. This only affects the local
    # test runner - the real app always runs inside a Linux container.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://rag:rag@localhost:5432/rag"
)
os.environ["TESTING"] = "1"

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parent.parent

_TABLES_IN_FK_ORDER = (
    "query_logs",
    "messages",
    "conversations",
    "ingestion_jobs",
    "chunks",
    "documents",
    "collections",
    "rate_limit_buckets",
    "api_keys",
    "users",
)


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return cfg


@pytest.fixture(scope="session")
def _migrated_schema() -> None:
    """Brings the test database schema to head once per test session. Only requested
    by integration tests (via `_clean_tables`) so pure-logic tests never need a live DB.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def _clean_tables(_migrated_schema: None) -> AsyncGenerator[None, None]:
    async with AsyncSessionLocal() as session:
        await session.execute(text(f"TRUNCATE TABLE {', '.join(_TABLES_IN_FK_ORDER)} RESTART IDENTITY CASCADE"))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def create_user_and_key(client: AsyncClient, email: str | None = None) -> dict:
    """Signs up a fresh user, logs them in, and mints an API key. Returns a dict with
    email/password/user_id/token/api_key for convenience in tests.
    """
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    password = "correct-horse-battery-staple"

    signup = await client.post("/auth/signup", json={"email": email, "password": password})
    assert signup.status_code == 201, signup.text
    token = signup.json()["access_token"]
    user_id = signup.json()["user"]["id"]

    key_resp = await client.post("/keys", json={"name": "test-key"}, headers={"Authorization": f"Bearer {token}"})
    assert key_resp.status_code == 201, key_resp.text
    api_key = key_resp.json()["full_key"]

    return {"email": email, "password": password, "user_id": user_id, "token": token, "api_key": api_key}


async def create_collection(client: AsyncClient, api_key: str, name: str = "test-collection") -> dict:
    resp = await client.post(
        "/collections", json={"name": name}, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
