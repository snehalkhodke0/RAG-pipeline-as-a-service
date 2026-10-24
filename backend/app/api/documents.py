"""Document upload (multipart + URL), listing, deletion, and ingestion-job status routes.

Uploads are validated and persisted as `Document` + `IngestionJob` rows here and return
202 immediately. The actual parse/chunk/embed pipeline is wired in as a background task
in a later phase (see `app.services.ingestion`); until then jobs are created QUEUED.
"""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import Principal, get_rate_limited_principal, require_collection, require_document
from app.core.exceptions import FileTooLargeError, NotFoundError, UnsupportedFileError, UpstreamServiceError
from app.database import get_db
from app.models.collection import Collection
from app.models.document import Document, DocumentStatus, SourceType
from app.models.ingestion_job import IngestionJob, JobStage, JobStatus
from app.schemas.document import DocumentOut, UploadAcceptedResponse, UploadUrlRequest
from app.schemas.job import JobOut
from app.utils.mime import sniff_source_type

router = APIRouter(tags=["documents"])


async def _find_existing_document(db: AsyncSession, collection_id: uuid.UUID, content_hash: str) -> Document | None:
    result = await db.execute(
        select(Document).where(Document.collection_id == collection_id, Document.content_hash == content_hash)
    )
    return result.scalar_one_or_none()


async def _latest_job_for(db: AsyncSession, document_id: uuid.UUID) -> IngestionJob:
    result = await db.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id).order_by(IngestionJob.id.desc())
    )
    job = result.scalars().first()
    if job is None:
        # Should not happen in practice: every document is created together with a job.
        job = IngestionJob(document_id=document_id, status=JobStatus.QUEUED, stage=JobStage.QUEUED)
        db.add(job)
        await db.flush()
    return job


async def _create_document_and_job(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    collection: Collection,
    filename: str,
    source_type: SourceType,
    content: bytes,
    content_hash: str,
    source_url: str | None,
) -> tuple[Document, IngestionJob]:
    document = Document(
        collection_id=collection.id,
        filename=filename,
        source_type=source_type,
        source_url=source_url,
        content_hash=content_hash,
        file_size=len(content),
        status=DocumentStatus.QUEUED,
    )
    db.add(document)
    await db.flush()

    job = IngestionJob(document_id=document.id, status=JobStatus.QUEUED, stage=JobStage.QUEUED)
    db.add(job)

    try:
        await db.commit()
    except IntegrityError:
        # Lost a race against a concurrent identical upload; fall back to the row that won.
        await db.rollback()
        existing = await _find_existing_document(db, collection.id, content_hash)
        if existing is None:
            raise
        existing_job = await _latest_job_for(db, existing.id)
        await db.commit()
        return existing, existing_job

    await db.refresh(document)
    await db.refresh(job)

    from app.services.ingestion import run_ingestion_job

    background_tasks.add_task(run_ingestion_job, document.id, job.id, content)

    return document, job


@router.post(
    "/collections/{collection_id}/documents",
    response_model=UploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection: Collection = Depends(require_collection),
    db: AsyncSession = Depends(get_db),
) -> UploadAcceptedResponse:
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise FileTooLargeError(f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit.")

    filename = file.filename or "upload"
    source_type = sniff_source_type(filename, content)
    if source_type is None:
        raise UnsupportedFileError("Unsupported or unrecognized file type.")

    content_hash = hashlib.sha256(content).hexdigest()
    existing = await _find_existing_document(db, collection.id, content_hash)
    if existing is not None:
        job = await _latest_job_for(db, existing.id)
        await db.commit()
        return UploadAcceptedResponse(document_id=existing.id, job_id=job.id, status=existing.status)

    document, job = await _create_document_and_job(
        db, background_tasks, collection, filename, source_type, content, content_hash, source_url=None
    )
    return UploadAcceptedResponse(document_id=document.id, job_id=job.id, status=document.status)


@router.post(
    "/collections/{collection_id}/documents/url",
    response_model=UploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_from_url(
    payload: UploadUrlRequest,
    background_tasks: BackgroundTasks,
    collection: Collection = Depends(require_collection),
    db: AsyncSession = Depends(get_db),
) -> UploadAcceptedResponse:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(payload.url)
            response.raise_for_status()
            content = response.content
    except httpx.HTTPError as exc:
        raise UpstreamServiceError(f"Failed to fetch URL: {exc}") from exc

    if len(content) > settings.max_file_size_bytes:
        raise FileTooLargeError(f"Fetched content exceeds the {settings.MAX_FILE_SIZE_MB}MB limit.")

    parsed = urlparse(payload.url)
    filename = parsed.path.rsplit("/", 1)[-1] or parsed.netloc

    source_type = sniff_source_type(filename or "page.html", content)
    if source_type is None:
        # Most fetched pages are HTML without a recognizable extension; default to HTML
        # since the content type isn't PDF/DOCX/Markdown and came from a URL fetch.
        source_type = SourceType.HTML

    content_hash = hashlib.sha256(content).hexdigest()
    existing = await _find_existing_document(db, collection.id, content_hash)
    if existing is not None:
        job = await _latest_job_for(db, existing.id)
        await db.commit()
        return UploadAcceptedResponse(document_id=existing.id, job_id=job.id, status=existing.status)

    document, job = await _create_document_and_job(
        db, background_tasks, collection, filename or payload.url, source_type, content, content_hash, payload.url
    )
    return UploadAcceptedResponse(document_id=document.id, job_id=job.id, status=document.status)


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    collection: Collection = Depends(require_collection),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    result = await db.execute(
        select(Document).where(Document.collection_id == collection.id).order_by(Document.created_at.desc())
    )
    return [DocumentOut.model_validate(d) for d in result.scalars().all()]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_document(
    document: Document = Depends(require_document),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.delete(document)
    await db.commit()


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_rate_limited_principal),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    result = await db.execute(
        select(IngestionJob)
        .join(Document, Document.id == IngestionJob.document_id)
        .join(Collection, Collection.id == Document.collection_id)
        .where(IngestionJob.id == job_id, Collection.user_id == principal.user_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found.")
    return JobOut.model_validate(job)
