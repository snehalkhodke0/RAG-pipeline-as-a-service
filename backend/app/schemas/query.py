from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    score: float
    filename: str
    page_number: Optional[int]
    section_title: Optional[str]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    document_id: Optional[uuid.UUID] = None
    page_from: Optional[int] = Field(default=None, ge=1)
    page_to: Optional[int] = Field(default=None, ge=1)
    conversation_id: Optional[uuid.UUID] = None


class CitationOut(BaseModel):
    marker: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: Optional[int]
    snippet: str


class TimingsOut(BaseModel):
    retrieval_ms: int
    llm_ms: int
    total_ms: int


class UsageOut(BaseModel):
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    timings: TimingsOut
    usage: UsageOut
    conversation_id: Optional[uuid.UUID] = None
    condensed_query: Optional[str] = None
