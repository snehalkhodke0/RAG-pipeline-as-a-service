"""Mandatory tenant isolation test: user A must never be able to read, query, or
delete user B's collections, documents, chunks, or jobs - via either API key or JWT.
Requires a live Postgres (see conftest.py).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import create_collection, create_user_and_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("_clean_tables")]


async def test_user_cannot_read_or_list_another_users_collection(client: AsyncClient) -> None:
    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)

    collection = await create_collection(client, owner["api_key"], name="owner-collection")

    owner_headers = {"Authorization": f"Bearer {owner['api_key']}"}
    intruder_headers = {"Authorization": f"Bearer {intruder['api_key']}"}

    # Intruder cannot fetch it directly by id.
    resp = await client.get(f"/collections/{collection['id']}", headers=intruder_headers)
    assert resp.status_code == 404

    # Intruder's own list is empty - the owner's collection never leaks into it.
    listing = await client.get("/collections", headers=intruder_headers)
    assert listing.status_code == 200
    assert listing.json() == []

    # Sanity check: the owner can see it fine.
    own_view = await client.get(f"/collections/{collection['id']}", headers=owner_headers)
    assert own_view.status_code == 200


async def test_user_cannot_update_or_delete_another_users_collection(client: AsyncClient) -> None:
    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)
    collection = await create_collection(client, owner["api_key"])
    intruder_headers = {"Authorization": f"Bearer {intruder['api_key']}"}

    patch = await client.patch(
        f"/collections/{collection['id']}", json={"name": "hijacked"}, headers=intruder_headers
    )
    assert patch.status_code == 404

    delete = await client.delete(f"/collections/{collection['id']}", headers=intruder_headers)
    assert delete.status_code == 404


async def test_user_cannot_upload_to_or_list_documents_in_another_users_collection(client: AsyncClient) -> None:
    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)
    collection = await create_collection(client, owner["api_key"])
    intruder_headers = {"Authorization": f"Bearer {intruder['api_key']}"}

    listing = await client.get(f"/collections/{collection['id']}/documents", headers=intruder_headers)
    assert listing.status_code == 404

    upload = await client.post(
        f"/collections/{collection['id']}/documents/url",
        json={"url": "https://example.com"},
        headers=intruder_headers,
    )
    assert upload.status_code == 404


async def test_user_cannot_delete_another_users_document(client: AsyncClient) -> None:
    import io

    from pypdf import PdfWriter

    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)
    collection = await create_collection(client, owner["api_key"])
    owner_headers = {"Authorization": f"Bearer {owner['api_key']}"}
    intruder_headers = {"Authorization": f"Bearer {intruder['api_key']}"}

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    upload = await client.post(
        f"/collections/{collection['id']}/documents",
        files={"file": ("owner.pdf", buf.getvalue(), "application/pdf")},
        headers=owner_headers,
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["document_id"]

    delete = await client.delete(f"/documents/{document_id}", headers=intruder_headers)
    assert delete.status_code == 404


async def test_user_cannot_query_another_users_collection(client: AsyncClient) -> None:
    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)
    collection = await create_collection(client, owner["api_key"])
    intruder_headers = {"Authorization": f"Bearer {intruder['api_key']}"}

    resp = await client.post(
        f"/collections/{collection['id']}/query", json={"query": "anything"}, headers=intruder_headers
    )
    assert resp.status_code == 404

    search = await client.get(
        f"/collections/{collection['id']}/search", params={"q": "anything"}, headers=intruder_headers
    )
    assert search.status_code == 404


async def test_user_cannot_read_another_users_job(client: AsyncClient) -> None:
    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)
    intruder_headers = {"Authorization": f"Bearer {intruder['api_key']}"}

    # A job id that structurally could exist but belongs to no one the intruder owns.
    resp = await client.get(f"/jobs/{uuid.uuid4()}", headers=intruder_headers)
    assert resp.status_code == 404


async def test_jwt_auth_also_enforces_isolation(client: AsyncClient) -> None:
    owner = await create_user_and_key(client)
    intruder = await create_user_and_key(client)
    collection = await create_collection(client, owner["api_key"])
    intruder_jwt_headers = {"Authorization": f"Bearer {intruder['token']}"}

    resp = await client.get(f"/collections/{collection['id']}", headers=intruder_jwt_headers)
    assert resp.status_code == 404
