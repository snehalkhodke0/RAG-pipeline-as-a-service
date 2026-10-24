"""Structured JSON logging configuration and request-id context propagation."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from app.config import settings

request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JSONFormatter(logging.Formatter):
    """Renders every log record as a single line of JSON with a request_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configures the root logger to emit structured JSON to stdout exactly once."""
    root = logging.getLogger()
    if getattr(root, "_rag_configured", False):
        return
    root.setLevel(settings.LOG_LEVEL.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root._rag_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_with_fields(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Logs `message` at `level` attaching `fields` as extra structured data."""
    logger.log(level, message, extra={"extra_fields": fields})
