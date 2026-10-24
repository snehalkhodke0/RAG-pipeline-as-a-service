"""Mandatory idempotency test: uploading the same file twice creates exactly one
document. Requires a live Postgres (see conftest.py).
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

from tests.conftest import create_collection, create_user_and_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("_clean_tables")]


def _sample_pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def test_uploading_identical_file_twice_creates_one_document(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    collection = await create_collection(client, identity["api_key"])
    headers = {"Authorization": f"Bearer {identity['api_key']}"}
    content = _sample_pdf_bytes()

    first = await client.post(
        f"/collections/{collection['id']}/documents",
        files={"file": ("sample.pdf", content, "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 202, first.text
    first_document_id = first.json()["document_id"]

    second = await client.post(
        f"/collections/{collection['id']}/documents",
        files={"file": ("sample.pdf", content, "application/pdf")},
        headers=headers,
    )
    assert second.status_code == 202, second.text
    second_document_id = second.json()["document_id"]

    assert first_document_id == second_document_id

    listing = await client.get(f"/collections/{collection['id']}/documents", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_different_files_create_separate_documents(client: AsyncClient) -> None:
    identity = await create_user_and_key(client)
    collection = await create_collection(client, identity["api_key"])
    headers = {"Authorization": f"Bearer {identity['api_key']}"}

    await client.post(
        f"/collections/{collection['id']}/documents",
        files={"file": ("a.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    )

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)  # different content -> different hash
    buf = io.BytesIO()
    writer.write(buf)

    await client.post(
        f"/collections/{collection['id']}/documents",
        files={"file": ("b.pdf", buf.getvalue(), "application/pdf")},
        headers=headers,
    )

    listing = await client.get(f"/collections/{collection['id']}/documents", headers=headers)
    assert len(listing.json()) == 2
