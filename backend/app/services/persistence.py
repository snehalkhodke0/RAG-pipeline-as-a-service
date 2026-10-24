"""Embeds chunk text in batches and persists the resulting `Chunk` rows.

The embedding model itself is loaded exactly once at process startup (see
`app.services.embedding.get_embedding_service`); this module only ever calls into that
already-loaded singleton, batching requests as they arrive so a single large document
never holds the whole embedding matrix in memory at once.
"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chunk import Chunk
from app.services.chunking import DocumentChunk
from app.services.embedding import get_embedding_service

ProgressCallback = Optional[Callable[[int, int], Awaitable[None]]]


async def persist_chunks(
    db: AsyncSession,
    document_id: uuid.UUID,
    collection_id: uuid.UUID,
    chunks: List[DocumentChunk],
    batch_size: int = settings.EMBEDDING_BATCH_SIZE,
    on_batch_complete: ProgressCallback = None,
) -> int:
    """Embeds and inserts `chunks` in batches of `batch_size`. Returns the count inserted."""
    if not chunks:
        return 0

    embedding_service = get_embedding_service()
    total = len(chunks)
    inserted = 0

    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embedding_service.embed([c.content for c in batch], batch_size=len(batch))

        rows = [
            Chunk(
                document_id=document_id,
                collection_id=collection_id,
                content=chunk.content,
                embedding=vector,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                token_count=chunk.token_count,
            )
            for chunk, vector in zip(batch, vectors)
        ]
        db.add_all(rows)
        await db.flush()

        inserted += len(rows)
        if on_batch_complete is not None:
            await on_batch_complete(inserted, total)

    return inserted
