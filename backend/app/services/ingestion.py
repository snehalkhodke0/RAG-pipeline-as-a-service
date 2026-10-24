"""Async ingestion pipeline: PARSING -> CHUNKING -> EMBEDDING -> READY (or FAILED).

Runs as a FastAPI `BackgroundTasks` coroutine, scheduled right after the upload request
returns its 202. It opens its own database session (the request's session is closed by
the time this runs) and guarantees a terminal job/document status no matter what fails.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.exceptions import AppError
from app.core.logging import get_logger, log_with_fields
from app.database import AsyncSessionLocal
from app.models.collection import Collection
from app.models.document import Document, DocumentStatus
from app.models.ingestion_job import IngestionJob, JobStage, JobStatus
from app.services.chunking import chunk_document
from app.services.parsing import parse_document
from app.services.persistence import persist_chunks

logger = get_logger("app.services.ingestion")

# Progress checkpoints, in percent, for each pipeline stage.
_PROGRESS_PARSING_DONE = 15
_PROGRESS_CHUNKING_DONE = 30
_PROGRESS_EMBEDDING_START = 30
_PROGRESS_EMBEDDING_END = 95
_PROGRESS_READY = 100


async def run_ingestion_job(document_id: uuid.UUID, job_id: uuid.UUID, content: bytes) -> None:
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, document_id)
        job = await db.get(IngestionJob, job_id)
        if document is None or job is None:
            log_with_fields(
                logger, 30, "ingestion_job_target_missing", document_id=str(document_id), job_id=str(job_id)
            )
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.stage = JobStage.PARSING
        job.progress_pct = 0
        document.status = DocumentStatus.PARSING
        await db.commit()

        try:
            parsed = parse_document(document.source_type, content)
            document.page_count = parsed.page_count
            job.progress_pct = _PROGRESS_PARSING_DONE
            await db.commit()

            job.stage = JobStage.CHUNKING
            document.status = DocumentStatus.CHUNKING
            await db.commit()

            collection = await db.get(Collection, document.collection_id)
            if collection is None:
                raise AppError("Parent collection no longer exists.", code="collection_missing")

            chunks = chunk_document(parsed, collection.chunk_size, collection.chunk_overlap)
            job.progress_pct = _PROGRESS_CHUNKING_DONE
            await db.commit()

            job.stage = JobStage.EMBEDDING
            document.status = DocumentStatus.EMBEDDING
            await db.commit()

            async def on_batch_complete(done: int, total: int) -> None:
                span = _PROGRESS_EMBEDDING_END - _PROGRESS_EMBEDDING_START
                job.progress_pct = _PROGRESS_EMBEDDING_START + int(span * done / total)
                await db.commit()

            inserted = await persist_chunks(
                db, document.id, document.collection_id, chunks, on_batch_complete=on_batch_complete
            )

            document.chunk_count = inserted
            document.status = DocumentStatus.READY
            job.status = JobStatus.SUCCEEDED
            job.stage = JobStage.READY
            job.progress_pct = _PROGRESS_READY
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()

            log_with_fields(
                logger, 20, "ingestion_job_succeeded", document_id=str(document_id), chunks=inserted
            )

        except Exception as exc:  # noqa: BLE001 - any failure must still reach a terminal state
            log_with_fields(
                logger, 40, "ingestion_job_failed", document_id=str(document_id), error=str(exc)
            )
            await db.rollback()
            document = await db.get(Document, document_id)
            job = await db.get(IngestionJob, job_id)
            error_message = str(exc)[:2000]
            if document is not None:
                document.status = DocumentStatus.FAILED
                document.error_message = error_message
            if job is not None:
                job.status = JobStatus.FAILED
                job.stage = JobStage.FAILED
                job.error_message = error_message
                job.finished_at = datetime.now(timezone.utc)
            await db.commit()
