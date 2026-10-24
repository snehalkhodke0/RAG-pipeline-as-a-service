"""Collection CRUD routes. Every route resolves its collection through
`require_collection`, which scopes the lookup to `principal.user_id` - this is the
single enforcement point for tenant isolation on collections.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import Principal, get_rate_limited_principal, require_collection
from app.core.exceptions import ConflictError
from app.database import get_db
from app.models.collection import Collection
from app.schemas.collection import (
    CollectionOut,
    CreateCollectionRequest,
    UpdateCollectionRequest,
    resolve_chunk_params,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CreateCollectionRequest,
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> CollectionOut:
    chunk_size, chunk_overlap = resolve_chunk_params(payload.chunk_size, payload.chunk_overlap)
    collection = Collection(
        user_id=principal.user_id,
        name=payload.name,
        description=payload.description,
        embedding_model=settings.EMBEDDING_MODEL,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    db.add(collection)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A collection with this name already exists.") from exc
    await db.refresh(collection)
    return CollectionOut.model_validate(collection)


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> list[CollectionOut]:
    result = await db.execute(
        select(Collection).where(Collection.user_id == principal.user_id).order_by(Collection.created_at.desc())
    )
    return [CollectionOut.model_validate(c) for c in result.scalars().all()]


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(collection: Collection = Depends(require_collection)) -> CollectionOut:
    return CollectionOut.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    payload: UpdateCollectionRequest,
    collection: Collection = Depends(require_collection),
    db: AsyncSession = Depends(get_db),
) -> CollectionOut:
    if payload.name is not None:
        collection.name = payload.name
    if payload.description is not None:
        collection.description = payload.description
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A collection with this name already exists.") from exc
    await db.refresh(collection)
    return CollectionOut.model_validate(collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_collection(
    collection: Collection = Depends(require_collection),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.delete(collection)
    await db.commit()
