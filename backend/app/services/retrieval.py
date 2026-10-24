"""Hybrid retrieval: pgvector cosine-distance search + Postgres full-text search,
fused with Reciprocal Rank Fusion. Every query is scoped to a single collection_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.rrf import reciprocal_rank_fusion


@dataclass
class RetrievalFilters:
    document_id: Optional[uuid.UUID] = None
    page_from: Optional[int] = None
    page_to: Optional[int] = None


@dataclass
class RetrievalResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    score: float
    filename: str
    page_number: Optional[int]
    section_title: Optional[str]


def _apply_filters(stmt: Select, collection_id: uuid.UUID, filters: Optional[RetrievalFilters]) -> Select:
    stmt = stmt.where(Chunk.collection_id == collection_id)
    if filters is None:
        return stmt
    if filters.document_id is not None:
        stmt = stmt.where(Chunk.document_id == filters.document_id)
    if filters.page_from is not None:
        stmt = stmt.where(Chunk.page_number >= filters.page_from)
    if filters.page_to is not None:
        stmt = stmt.where(Chunk.page_number <= filters.page_to)
    return stmt


async def _vector_candidates(
    db: AsyncSession, collection_id: uuid.UUID, query_embedding: List[float], filters: Optional[RetrievalFilters]
) -> List[uuid.UUID]:
    stmt = select(Chunk.id)
    stmt = _apply_filters(stmt, collection_id, filters)
    stmt = stmt.order_by(Chunk.embedding.cosine_distance(query_embedding)).limit(settings.VECTOR_CANDIDATES)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _keyword_candidates(
    db: AsyncSession, collection_id: uuid.UUID, query_text: str, filters: Optional[RetrievalFilters]
) -> List[uuid.UUID]:
    tsquery = func.plainto_tsquery("english", query_text)
    stmt = select(Chunk.id).where(Chunk.content_tsv.op("@@")(tsquery))
    stmt = _apply_filters(stmt, collection_id, filters)
    stmt = stmt.order_by(func.ts_rank_cd(Chunk.content_tsv, tsquery).desc()).limit(settings.KEYWORD_CANDIDATES)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def hybrid_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    query_text: str,
    query_embedding: List[float],
    top_k: int = settings.DEFAULT_TOP_K,
    filters: Optional[RetrievalFilters] = None,
    mode: str = "hybrid",
) -> List[RetrievalResult]:
    """Retrieves and fuses candidates. `mode` is "hybrid" (default), "vector", or
    "keyword" - the latter two exist for the eval harness's ablation comparisons.
    """
    ranked_lists: List[List[uuid.UUID]] = []

    if mode in ("hybrid", "vector"):
        ranked_lists.append(await _vector_candidates(db, collection_id, query_embedding, filters))
    if mode in ("hybrid", "keyword"):
        ranked_lists.append(await _keyword_candidates(db, collection_id, query_text, filters))

    fused = reciprocal_rank_fusion(ranked_lists, k=settings.RRF_K)
    top_ids = [chunk_id for chunk_id, _ in fused[:top_k]]
    if not top_ids:
        return []

    score_by_id = dict(fused)
    rows_stmt = (
        select(Chunk, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_(top_ids))
    )
    rows = await db.execute(rows_stmt)
    by_id = {chunk.id: (chunk, filename) for chunk, filename in rows.all()}

    results: List[RetrievalResult] = []
    for chunk_id in top_ids:
        pair = by_id.get(chunk_id)
        if pair is None:
            continue
        chunk, filename = pair
        results.append(
            RetrievalResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=score_by_id[chunk_id],
                filename=filename,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
            )
        )
    return results
