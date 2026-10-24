"""Integration tests for signup/login/me and API key issuance. Requires a live
Postgres (see conftest.py) - run via `docker-compose up -d db` first.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import create_user_and_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("_clean_tables")]


async def test_signup_login_me_flow(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)

    login = await client.post("/auth/login", json={"email": identity["email"], "password": identity["password"]})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == identity["email"]


async def test_signup_duplicate_email_conflicts(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    resp = await client.post("/auth/signup", json={"email": identity["email"], "password": "another-password"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


async def test_login_wrong_password_unauthorized(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    resp = await client.post("/auth/login", json={"email": identity["email"], "password": "wrong-password"})
    assert resp.status_code == 401


async def test_api_key_shown_once_and_not_in_list(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    headers = {"Authorization": f"Bearer {identity['token']}"}

    listing = await client.get("/keys", headers=headers)
    assert listing.status_code == 200
    keys = listing.json()
    assert len(keys) == 1
    assert "full_key" not in keys[0]
    assert keys[0]["prefix"] == identity["api_key"][:12]


async def test_revoked_key_is_rejected(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    headers = {"Authorization": f"Bearer {identity['token']}"}

    listing = await client.get("/keys", headers=headers)
    key_id = listing.json()[0]["id"]

    revoke = await client.delete(f"/keys/{key_id}", headers=headers)
    assert revoke.status_code == 204

    resp = await client.post(
        "/collections", json={"name": "x"}, headers={"Authorization": f"Bearer {identity['api_key']}"}
    )
    assert resp.status_code == 401


async def test_api_key_authenticates_collection_routes(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    resp = await client.get("/collections", headers={"Authorization": f"Bearer {identity['api_key']}"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_jwt_also_authenticates_collection_routes(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    resp = await client.get("/collections", headers={"Authorization": f"Bearer {identity['token']}"})
    assert resp.status_code == 200
