from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CreateKeyResponse(BaseModel):
    id: uuid.UUID
    full_key: str
    prefix: str
    name: str


class ApiKeyOut(ORMModel):
    id: uuid.UUID
    name: str
    prefix: str = Field(validation_alias="key_prefix")
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime
