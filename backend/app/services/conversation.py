"""Conversation memory: loading history for query condensation and persisting turns.

A conversation is scoped to a collection; ownership is enforced by the caller always
filtering `Conversation.collection_id` to a collection already resolved through
`require_collection` (which itself scopes to the caller's user_id) - so a client can
never read or extend another tenant's conversation.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.services.generation import Citation

MAX_HISTORY_MESSAGES = 10


async def get_or_create_conversation(
    db: AsyncSession, collection_id: uuid.UUID, api_key_id: uuid.UUID, conversation_id: Optional[uuid.UUID]
) -> Conversation:
    if conversation_id is not None:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.collection_id == collection_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    conversation = Conversation(
        id=conversation_id or uuid.uuid4(), collection_id=collection_id, api_key_id=api_key_id
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def load_history(db: AsyncSession, conversation_id: uuid.UUID) -> List[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    return [{"role": m.role, "content": m.content} for m in result.scalars().all()]


async def record_turn(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_query: str,
    answer: str,
    citations: List[Citation],
) -> None:
    db.add(Message(conversation_id=conversation_id, role=MessageRole.USER, content=user_query, citations=[]))
    db.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            citations=[
                {
                    "marker": c.marker,
                    "chunk_id": str(c.chunk_id),
                    "document_id": str(c.document_id),
                    "filename": c.filename,
                    "page_number": c.page_number,
                    "snippet": c.snippet,
                }
                for c in citations
            ],
        )
    )
    await db.flush()
