"""Mandatory retrieval test: results are scoped to the queried collection_id even when
another collection holds near-identical content. Requires a live Postgres.

Chunks are inserted directly (bypassing the upload/parsing pipeline) so this test is
deterministic and has no external network dependency; it still exercises the real
pgvector cosine search, the real tsvector keyword search, and the real RRF fusion.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document, DocumentStatus, SourceType
from app.models.user import User
from app.services.embedding import get_embedding_service
from app.services.retrieval import hybrid_search

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("_clean_tables")]


async def _make_user(db: AsyncSession) -> User:
    user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _make_collection(db: AsyncSession, user: User, name: str) -> Collection:
    collection = Collection(
        user_id=user.id, name=name, embedding_model="BAAI/bge-small-en-v1.5", chunk_size=512, chunk_overlap=64
    )
    db.add(collection)
    await db.flush()
    return collection


async def _make_document(db: AsyncSession, collection: Collection, filename: str) -> Document:
    document = Document(
        collection_id=collection.id,
        filename=filename,
        source_type=SourceType.MARKDOWN,
        content_hash=uuid.uuid4().hex,
        file_size=100,
        status=DocumentStatus.READY,
    )
    db.add(document)
    await db.flush()
    return document


async def _add_chunk(db: AsyncSession, document: Document, collection: Collection, text: str, index: int) -> None:
    vector = get_embedding_service().embed_one(text)
    db.add(
        Chunk(
            document_id=document.id,
            collection_id=collection.id,
            content=text,
            embedding=vector,
            chunk_index=index,
            page_number=1,
            token_count=len(text.split()),
        )
    )


async def test_retrieval_is_scoped_to_collection(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    collection_a = await _make_collection(db_session, user, "collection-a")
    collection_b = await _make_collection(db_session, user, "collection-b")
    doc_a = await _make_document(db_session, collection_a, "a.md")
    doc_b = await _make_document(db_session, collection_b, "b.md")

    # Deliberately near-identical content in both collections.
    await _add_chunk(db_session, doc_a, collection_a, "The giraffe is the tallest living terrestrial animal.", 0)
    await _add_chunk(db_session, doc_b, collection_b, "The giraffe is the tallest living terrestrial animal.", 0)
    await db_session.commit()

    query_embedding = get_embedding_service().embed_query("What is the tallest land animal?")

    results_a = await hybrid_search(db_session, collection_a.id, "tallest land animal", query_embedding, top_k=5)
    results_b = await hybrid_search(db_session, collection_b.id, "tallest land animal", query_embedding, top_k=5)

    assert len(results_a) == 1
    assert results_a[0].document_id == doc_a.id
    assert len(results_b) == 1
    assert results_b[0].document_id == doc_b.id

    # An empty collection returns nothing, never bleeding in another collection's chunks.
    collection_c = await _make_collection(db_session, user, "collection-c")
    await db_session.commit()
    results_c = await hybrid_search(db_session, collection_c.id, "tallest land animal", query_embedding, top_k=5)
    assert results_c == []


async def test_hybrid_beats_single_mode_on_keyword_heavy_query(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    collection = await _make_collection(db_session, user, "mixed")
    document = await _make_document(db_session, collection, "doc.md")

    await _add_chunk(db_session, document, collection, "SKU-48213 ships in blue, red, and green variants.", 0)
    await _add_chunk(db_session, document, collection, "Our return policy allows exchanges within 30 days.", 1)
    await db_session.commit()

    # An exact SKU token match is something keyword search nails and vector search may not.
    query_embedding = get_embedding_service().embed_query("SKU-48213")
    keyword_results = await hybrid_search(
        db_session, collection.id, "SKU-48213", query_embedding, top_k=5, mode="keyword"
    )
    assert keyword_results
    assert "SKU-48213" in keyword_results[0].content
