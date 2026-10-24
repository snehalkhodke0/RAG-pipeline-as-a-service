"""Persists one `query_logs` row per /query or /query/stream call, and also emits a
structured log line carrying both the original and any condensed (multi-turn) query
text - the query_logs table's fixed schema has a single `query` column, so the
before/after condensation pair is recorded in the structured application log instead.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, log_with_fields
from app.models.query_log import QueryLog

logger = get_logger("app.services.query_log")


async def record_query_log(
    db: AsyncSession,
    api_key_id: uuid.UUID,
    collection_id: uuid.UUID,
    original_query: str,
    condensed_query: Optional[str],
    retrieval_ms: int,
    llm_ms: int,
    total_ms: int,
    chunks_retrieved: int,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> None:
    db.add(
        QueryLog(
            api_key_id=api_key_id,
            collection_id=collection_id,
            query=original_query,
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
            chunks_retrieved=chunks_retrieved,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    )
    await db.flush()

    if condensed_query is not None and condensed_query != original_query:
        log_with_fields(
            logger,
            20,
            "query_condensed",
            original_query=original_query,
            condensed_query=condensed_query,
            collection_id=str(collection_id),
        )
