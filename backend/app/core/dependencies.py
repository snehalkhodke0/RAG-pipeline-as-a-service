"""Shared FastAPI dependencies: authentication, the auth/api-key principal, and
tenant-ownership enforcement.

Every route that touches a collection, document, or chunk MUST resolve the resource
through one of the `require_*` dependencies here rather than querying it directly by id.
That is the single choke point that guarantees tenant isolation across the whole API.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.rate_limit import check_and_consume
from app.core.security import decode_access_token, generate_api_key, hash_api_key, looks_like_api_key
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.collection import Collection
from app.models.document import Document
from app.models.user import User

DASHBOARD_KEY_NAME = "__dashboard__"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller for API-key-or-JWT routes."""

    user_id: uuid.UUID
    api_key_id: uuid.UUID
    auth_method: str  # "api_key" | "jwt"


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Missing bearer token.")
    return token


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """JWT-only auth, for dashboard-identity routes (/auth/me, /keys/*)."""
    token = _extract_bearer_token(authorization)
    if looks_like_api_key(token):
        raise UnauthorizedError("This endpoint requires a dashboard login token, not an API key.")
    payload = decode_access_token(token)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid access token payload.") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("User for this token no longer exists.")
    return user


async def _get_or_create_dashboard_key(db: AsyncSession, user_id: uuid.UUID) -> ApiKey:
    """Every JWT-authenticated call into the API-key-authenticated surface (collections,
    documents, query) is attributed to a hidden, non-listable API key so that usage
    tracking, rate limiting, and query logging have a uniform api_key_id to key off of.
    This key's raw secret is never generated as a usable token and is never returned to
    any client - it exists purely as an attribution anchor.
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.name == DASHBOARD_KEY_NAME)
    )
    key = result.scalar_one_or_none()
    if key is not None:
        return key

    _full_key, key_hash, key_prefix = generate_api_key()
    key = ApiKey(
        user_id=user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=DASHBOARD_KEY_NAME,
        is_active=True,
    )
    db.add(key)
    await db.flush()
    return key


async def get_principal(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Accepts either `Authorization: Bearer rag_xxx` (API key) or a dashboard JWT."""
    token = _extract_bearer_token(authorization)

    if looks_like_api_key(token):
        key_hash = hash_api_key(token)
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        api_key = result.scalar_one_or_none()
        if api_key is None or not api_key.is_active:
            raise UnauthorizedError("Invalid or revoked API key.")
        api_key.last_used_at = datetime.now(timezone.utc)
        await db.flush()
        return Principal(user_id=api_key.user_id, api_key_id=api_key.id, auth_method="api_key")

    payload = decode_access_token(token)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid access token payload.") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        raise UnauthorizedError("User for this token no longer exists.")

    dashboard_key = await _get_or_create_dashboard_key(db, user_id)
    return Principal(user_id=user_id, api_key_id=dashboard_key.id, auth_method="jwt")


async def get_rate_limited_principal(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Same as `get_principal`, additionally enforcing the per-key token-bucket limit."""
    await check_and_consume(db, principal.api_key_id)
    return principal


async def require_collection(
    collection_id: uuid.UUID,
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> Collection:
    """Resolves a collection scoped to the caller's user_id. Returns 404 (never 403) for
    a collection that exists but is owned by someone else, so ownership can't be probed.
    """
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == principal.user_id)
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


async def require_document(
    document_id: uuid.UUID,
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Resolves a document scoped to the caller's user_id via its parent collection."""
    result = await db.execute(
        select(Document)
        .join(Collection, Collection.id == Document.collection_id)
        .where(Document.id == document_id, Collection.user_id == principal.user_id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found.")
    return document
