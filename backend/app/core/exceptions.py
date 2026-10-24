"""Application exception hierarchy and the shared error envelope."""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """Base class for all application errors that map to a clean HTTP response.

    Every subclass carries a machine-readable `code`, a human `message`, and the
    `status_code` to return. Handlers in `app.main` translate these into the
    `{"error": {"code", "message", "request_id"}}` envelope.
    """

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: Optional[str] = None, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class RateLimitExceededError(AppError):
    status_code = 429
    code = "rate_limit_exceeded"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file_type"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class UpstreamServiceError(AppError):
    status_code = 502
    code = "upstream_service_error"


def error_envelope(code: str, message: str, request_id: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}
