"""FastAPI application entrypoint: middleware, error handlers, router wiring."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.core.exceptions import AppError, error_envelope
from app.core.logging import configure_logging, get_logger, log_with_fields, request_id_ctx_var
from app.database import engine

configure_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Load the embedding model once at startup so no request ever pays a cold-load cost.
    from app.services.embedding import get_embedding_service

    get_embedding_service()
    log_with_fields(logger, 20, "startup_complete", app=settings.APP_NAME, version=settings.APP_VERSION)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Assigns a request_id, times the request, and logs a structured access line."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_ctx_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_ctx_var.reset(token)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    log_with_fields(
        logger,
        20,
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = request_id_ctx_var.get()
    headers = {}
    retry_after = getattr(exc, "retry_after_seconds", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    log_with_fields(logger, 30, "app_error", code=exc.code, error_message=exc.message, status_code=exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.code, exc.message, request_id),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request_id_ctx_var.get()
    message = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_envelope("validation_error", message, request_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request_id_ctx_var.get()
    logger.exception("unhandled_exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_envelope("internal_error", "An unexpected error occurred.", request_id),
    )


@app.get("/health", tags=["system"])
async def health() -> dict:
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health check must report, not raise
        db_status = f"error: {exc.__class__.__name__}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "embedding_model": settings.EMBEDDING_MODEL,
        "version": settings.APP_VERSION,
    }


from app.api import auth, keys, collections, documents, query, admin  # noqa: E402

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(collections.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(admin.router)
