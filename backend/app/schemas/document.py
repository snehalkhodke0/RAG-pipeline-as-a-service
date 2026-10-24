from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class UploadUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class DocumentOut(ORMModel):
    id: uuid.UUID
    filename: str
    source_type: str
    source_url: Optional[str]
    file_size: int
    status: str
    page_count: Optional[int]
    chunk_count: int
    error_message: Optional[str]
    created_at: datetime


class UploadAcceptedResponse(BaseModel):
    document_id: uuid.UUID
    job_id: uuid.UUID
    status: str
