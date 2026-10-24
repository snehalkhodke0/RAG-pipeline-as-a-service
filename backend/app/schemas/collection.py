from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.schemas.common import ORMModel


class CreateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4096)
    chunk_size: Optional[int] = Field(default=None, ge=64, le=4096)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=2048)


class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4096)


class CollectionOut(ORMModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime


def resolve_chunk_params(chunk_size: Optional[int], chunk_overlap: Optional[int]) -> tuple[int, int]:
    size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP
    if overlap >= size:
        overlap = max(0, size // 4)
    return size, overlap
