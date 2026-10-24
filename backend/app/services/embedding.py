"""Embedding service: a process-wide singleton wrapping fastembed.

The model is loaded exactly once, at application startup (see `app.main.lifespan`),
never per-request, so request latency never pays a model-load cost and repeated
requests don't leak memory re-loading the ONNX session.
"""

from __future__ import annotations

import os
import threading
from typing import List, Optional

from app.config import settings
from app.core.logging import get_logger, log_with_fields

logger = get_logger("app.services.embedding")

_lock = threading.Lock()
_instance: Optional["EmbeddingService"] = None


class EmbeddingService:
    """Thin wrapper around fastembed's TextEmbedding model."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        cache_dir = os.environ.get("FASTEMBED_CACHE_PATH")
        log_with_fields(logger, 20, "embedding_model_loading", model=model_name, cache_dir=cache_dir)
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self.dimension = settings.EMBEDDING_DIM
        log_with_fields(logger, 20, "embedding_model_loaded", model=model_name)

    def embed(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Embeds a batch of texts, returning one 384-dim vector per text, in order."""
        if not texts:
            return []
        vectors = self._model.embed(texts, batch_size=batch_size)
        return [vector.tolist() for vector in vectors]

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]

    def embed_query(self, text: str) -> List[float]:
        """BGE models are trained asymmetrically: queries should carry an instruction
        prefix while indexed passages should not. This measurably improves retrieval
        quality over embedding the bare query text.
        """
        prefixed = f"Represent this sentence for searching relevant passages: {text}"
        return self.embed([prefixed])[0]


def get_embedding_service() -> EmbeddingService:
    """Returns the process-wide `EmbeddingService` singleton, creating it on first call."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EmbeddingService(settings.EMBEDDING_MODEL)
    return _instance
