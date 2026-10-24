from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.schemas.common import ORMModel


class JobOut(ORMModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    stage: str
    progress_pct: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
