"""API key management routes (dashboard/JWT auth only)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DASHBOARD_KEY_NAME, get_current_user
from app.core.exceptions import NotFoundError
from app.core.security import generate_api_key
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ApiKeyOut, CreateKeyRequest, CreateKeyResponse

router = APIRouter(prefix="/keys", tags=["api-keys"])


@router.post("", response_model=CreateKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: CreateKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateKeyResponse:
    full_key, key_hash, key_prefix = generate_api_key()
    key = ApiKey(user_id=current_user.id, key_hash=key_hash, key_prefix=key_prefix, name=payload.name)
    db.add(key)
    await db.commit()
    await db.refresh(key)

    return CreateKeyResponse(id=key.id, full_key=full_key, prefix=key.key_prefix, name=key.name)


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyOut]:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id, ApiKey.name != DASHBOARD_KEY_NAME)
        .order_by(ApiKey.created_at.desc())
    )
    return [ApiKeyOut.model_validate(k) for k in result.scalars().all()]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_key(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id, ApiKey.name != DASHBOARD_KEY_NAME)
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise NotFoundError("API key not found.")
    key.is_active = False
    await db.commit()
