"""Search (debug, no LLM), query, and streaming query routes."""

from __future__ import annotations

import json
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.config import settings
from app.core.dependencies import Principal, get_rate_limited_principal, require_collection
from app.database import get_db
from app.models.collection import Collection
from app.schemas.query import (
    CitationOut,
    QueryRequest,
    QueryResponse,
    SearchResponse,
    SearchResultOut,
    TimingsOut,
    UsageOut,
)
from app.services.conversation import get_or_create_conversation, load_history, record_turn
from app.services.embedding import get_embedding_service
from app.services.generation import condense_query, extract_citations, generate_answer, stream_answer
from app.services.query_log import record_query_log
from app.services.retrieval import RetrievalFilters, RetrievalResult, hybrid_search

router = APIRouter(tags=["query"])


@router.get("/collections/{collection_id}/search", response_model=SearchResponse)
async def search_collection(
    q: str = Query(min_length=1, max_length=2048),
    top_k: int = Query(default=5, ge=1, le=50),
    document_id: uuid.UUID | None = Query(default=None),
    page_from: int | None = Query(default=None, ge=1),
    page_to: int | None = Query(default=None, ge=1),
    mode: str = Query(default="hybrid", pattern="^(hybrid|vector|keyword)$"),
    collection: Collection = Depends(require_collection),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Raw retrieval debug endpoint: no LLM call, just the fused chunks. `mode` defaults
    to "hybrid" (vector + keyword + RRF); "vector" and "keyword" run single-signal
    retrieval and exist for the eval harness's ablation comparisons.
    """
    query_embedding = get_embedding_service().embed_query(q)
    filters = RetrievalFilters(document_id=document_id, page_from=page_from, page_to=page_to)

    results = await hybrid_search(db, collection.id, q, query_embedding, top_k=top_k, filters=filters, mode=mode)

    return SearchResponse(
        query=q,
        results=[
            SearchResultOut(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                content=r.content,
                score=r.score,
                filename=r.filename,
                page_number=r.page_number,
                section_title=r.section_title,
            )
            for r in results
        ],
    )


async def _resolve_query_and_history(
    db: AsyncSession,
    collection: Collection,
    principal: Principal,
    payload: QueryRequest,
) -> tuple[str, uuid.UUID | None]:
    """If a conversation_id is supplied, loads its history and - when there IS prior
    history - condenses the follow-up into a standalone query. Returns
    (query_to_retrieve_with, conversation_id_or_None).
    """
    if payload.conversation_id is None:
        return payload.query, None

    conversation = await get_or_create_conversation(
        db, collection.id, principal.api_key_id, payload.conversation_id
    )
    history = await load_history(db, conversation.id)
    if not history:
        return payload.query, conversation.id

    condensed = await condense_query(payload.query, history)
    return condensed, conversation.id


@router.post("/collections/{collection_id}/query", response_model=QueryResponse)
async def query_collection(
    payload: QueryRequest,
    collection: Collection = Depends(require_collection),
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    total_start = time.perf_counter()

    retrieval_query, conversation_id = await _resolve_query_and_history(db, collection, principal, payload)

    query_embedding = get_embedding_service().embed_query(retrieval_query)
    filters = RetrievalFilters(document_id=payload.document_id, page_from=payload.page_from, page_to=payload.page_to)

    retrieval_start = time.perf_counter()
    results = await hybrid_search(
        db,
        collection.id,
        retrieval_query,
        query_embedding,
        top_k=payload.top_k or settings.DEFAULT_TOP_K,
        filters=filters,
    )
    retrieval_ms = int((time.perf_counter() - retrieval_start) * 1000)

    generation = await generate_answer(retrieval_query, results)
    total_ms = int((time.perf_counter() - total_start) * 1000)

    if conversation_id is not None:
        await record_turn(db, conversation_id, payload.query, generation.answer, generation.citations)

    await record_query_log(
        db,
        principal.api_key_id,
        collection.id,
        payload.query,
        retrieval_query if retrieval_query != payload.query else None,
        retrieval_ms,
        generation.llm_ms,
        total_ms,
        len(results),
        generation.prompt_tokens,
        generation.completion_tokens,
    )
    await db.commit()

    return QueryResponse(
        answer=generation.answer,
        citations=[
            CitationOut(
                marker=c.marker,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                page_number=c.page_number,
                snippet=c.snippet,
            )
            for c in generation.citations
        ],
        timings=TimingsOut(retrieval_ms=retrieval_ms, llm_ms=generation.llm_ms, total_ms=total_ms),
        usage=UsageOut(prompt_tokens=generation.prompt_tokens, completion_tokens=generation.completion_tokens),
        conversation_id=conversation_id,
        condensed_query=retrieval_query if conversation_id is not None else None,
    )


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/collections/{collection_id}/query/stream")
async def query_collection_stream(
    payload: QueryRequest,
    collection: Collection = Depends(require_collection),
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Server-Sent Events stream: `token` deltas, then `citations`, then `done` with
    timings/usage - or a single `error` event if anything fails mid-stream.
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        total_start = time.perf_counter()
        try:
            retrieval_query, conversation_id = await _resolve_query_and_history(db, collection, principal, payload)

            query_embedding = get_embedding_service().embed_query(retrieval_query)
            filters = RetrievalFilters(
                document_id=payload.document_id, page_from=payload.page_from, page_to=payload.page_to
            )

            retrieval_start = time.perf_counter()
            results: list[RetrievalResult] = await hybrid_search(
                db,
                collection.id,
                retrieval_query,
                query_embedding,
                top_k=payload.top_k or settings.DEFAULT_TOP_K,
                filters=filters,
            )
            retrieval_ms = int((time.perf_counter() - retrieval_start) * 1000)

            answer_parts: list[str] = []
            prompt_tokens = None
            completion_tokens = None
            llm_start = time.perf_counter()

            async for event_type, value in stream_answer(retrieval_query, results):
                if event_type == "token":
                    answer_parts.append(str(value))
                    yield _sse_event("token", {"text": value})
                elif event_type == "usage":
                    prompt_tokens, completion_tokens = value  # type: ignore[misc]

            llm_ms = int((time.perf_counter() - llm_start) * 1000)
            full_answer = "".join(answer_parts)
            citations = extract_citations(full_answer, results)

            yield _sse_event(
                "citations",
                {
                    "citations": [
                        {
                            "marker": c.marker,
                            "chunk_id": str(c.chunk_id),
                            "document_id": str(c.document_id),
                            "filename": c.filename,
                            "page_number": c.page_number,
                            "snippet": c.snippet,
                        }
                        for c in citations
                    ]
                },
            )

            if conversation_id is not None:
                await record_turn(db, conversation_id, payload.query, full_answer, citations)

            total_ms = int((time.perf_counter() - total_start) * 1000)

            await record_query_log(
                db,
                principal.api_key_id,
                collection.id,
                payload.query,
                retrieval_query if retrieval_query != payload.query else None,
                retrieval_ms,
                llm_ms,
                total_ms,
                len(results),
                prompt_tokens,
                completion_tokens,
            )
            await db.commit()

            yield _sse_event(
                "done",
                {
                    "timings": {"retrieval_ms": retrieval_ms, "llm_ms": llm_ms, "total_ms": total_ms},
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
                    "conversation_id": str(conversation_id) if conversation_id else None,
                },
            )
        except Exception as exc:  # noqa: BLE001 - stream must degrade to an error event, not a bare 500
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
