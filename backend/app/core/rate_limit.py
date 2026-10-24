"""Token-bucket rate limiting, state persisted in Postgres (`rate_limit_buckets`) so it
is correct across multiple backend replicas rather than being per-process memory.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import RateLimitExceededError
from app.models.rate_limit_bucket import RateLimitBucket


async def check_and_consume(db: AsyncSession, api_key_id: uuid.UUID) -> None:
    """Consumes one token from the caller's bucket, raising `RateLimitExceededError`
    (HTTP 429 with a Retry-After header) when the bucket is empty.
    """
    capacity = float(settings.RATE_LIMIT_PER_MINUTE)
    refill_per_second = capacity / 60.0
    now = datetime.now(timezone.utc)

    insert_stmt = (
        pg_insert(RateLimitBucket)
        .values(api_key_id=api_key_id, tokens=capacity, updated_at=now)
        .on_conflict_do_nothing(index_elements=[RateLimitBucket.api_key_id])
    )
    await db.execute(insert_stmt)

    result = await db.execute(
        select(RateLimitBucket).where(RateLimitBucket.api_key_id == api_key_id).with_for_update()
    )
    bucket = result.scalar_one()

    elapsed_seconds = max(0.0, (now - bucket.updated_at).total_seconds())
    available = min(capacity, bucket.tokens + elapsed_seconds * refill_per_second)

    if available < 1.0:
        deficit = 1.0 - available
        retry_after = max(1, math.ceil(deficit / refill_per_second))
        await db.commit()
        raise RateLimitExceededError(
            f"Rate limit exceeded. Retry after {retry_after} second(s).",
            retry_after_seconds=retry_after,
        )

    bucket.tokens = available - 1.0
    bucket.updated_at = now
    await db.commit()
