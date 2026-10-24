"""Mandatory rate-limit test: exceeding the per-key token bucket returns 429 with a
Retry-After header. Requires a live Postgres.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import settings
from tests.conftest import create_user_and_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("_clean_tables")]


async def test_rate_limit_returns_429_with_retry_after(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)

    identity = await create_user_and_key(client)
    headers = {"Authorization": f"Bearer {identity['api_key']}"}

    first = await client.get("/collections", headers=headers)
    second = await client.get("/collections", headers=headers)
    third = await client.get("/collections", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Retry-After" in third.headers
    assert third.json()["error"]["code"] == "rate_limit_exceeded"


async def test_rate_limit_is_per_key_not_global(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)

    user_a = await create_user_and_key(client)
    user_b = await create_user_and_key(client)

    a_headers = {"Authorization": f"Bearer {user_a['api_key']}"}
    b_headers = {"Authorization": f"Bearer {user_b['api_key']}"}

    exhaust_a = await client.get("/collections", headers=a_headers)
    assert exhaust_a.status_code == 200

    limited_a = await client.get("/collections", headers=a_headers)
    assert limited_a.status_code == 429

    # User B has an independent bucket and is unaffected by A's exhaustion.
    still_ok_b = await client.get("/collections", headers=b_headers)
    assert still_ok_b.status_code == 200
