"""Usage totals and recent query-trace routes, both scoped to the caller's own API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, get_rate_limited_principal
from app.database import get_db
from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.models.query_log import QueryLog
from app.schemas.usage import QueryLogOut, UsageTotals

router = APIRouter(tags=["admin"])


@router.get("/usage", response_model=UsageTotals)
async def get_usage(
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> UsageTotals:
    query_stats = await db.execute(
        select(
            func.count(QueryLog.id),
            func.coalesce(func.sum(QueryLog.prompt_tokens), 0),
            func.coalesce(func.sum(QueryLog.completion_tokens), 0),
        ).where(QueryLog.api_key_id == principal.api_key_id)
    )
    queries, prompt_tokens, completion_tokens = query_stats.one()

    doc_count = await db.execute(
        select(func.count(Document.id))
        .join(Collection, Collection.id == Document.collection_id)
        .where(Collection.user_id == principal.user_id)
    )
    documents = doc_count.scalar_one()

    chunk_count = await db.execute(
        select(func.count(Chunk.id))
        .join(Collection, Collection.id == Chunk.collection_id)
        .where(Collection.user_id == principal.user_id)
    )
    chunks = chunk_count.scalar_one()

    return UsageTotals(
        api_key_id=principal.api_key_id,
        queries=queries,
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
        documents=documents,
        chunks=chunks,
    )


@router.get("/logs", response_model=list[QueryLogOut])
async def get_logs(
    limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> list[QueryLogOut]:
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.api_key_id == principal.api_key_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    return [QueryLogOut.model_validate(row, from_attributes=True) for row in result.scalars().all()]
