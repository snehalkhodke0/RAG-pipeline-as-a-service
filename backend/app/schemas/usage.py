from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UsageTotals(BaseModel):
    api_key_id: uuid.UUID
    queries: int
    prompt_tokens: int
    completion_tokens: int
    documents: int
    chunks: int


class QueryLogOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    query: str
    retrieval_ms: Optional[int]
    llm_ms: Optional[int]
    total_ms: Optional[int]
    chunks_retrieved: Optional[int]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    created_at: datetime
