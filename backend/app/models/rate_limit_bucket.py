"""Token-bucket rate-limit state, persisted in Postgres (not in-process memory) so it is
correct across multiple backend replicas. This is a supporting table beyond the 9 core
product tables, required by the rate-limiting spec ("token bucket per API key stored in
Postgres").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    api_key_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="CASCADE"), primary_key=True
    )
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
