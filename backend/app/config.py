"""Application configuration loaded from environment variables.

A single `Settings` instance (`settings`) is constructed at import time and reused
everywhere. Never read `os.environ` directly outside this module.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "RAG Pipeline as a Service"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://rag:rag@localhost:5432/rag")

    # LLM
    GROQ_API_KEY: str = Field(default="")
    # NOTE: llama-3.3-70b-versatile (the model named in the original spec) has been
    # deprecated and removed from Groq's API - it 404s with "model_not_found" as of
    # this deployment. openai/gpt-oss-120b is the closest currently-available
    # like-for-like substitute: a large (120B) general-purpose instruction-following
    # model, Groq-hosted, with the same streaming chat-completions interface.
    # Override via GROQ_MODEL if Groq's lineup changes again.
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # Auth
    JWT_SECRET: str = Field(default="dev-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 1440

    # Embeddings
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384

    # Chunking
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    MIN_CHUNK_TOKENS: int = 30

    # Uploads
    MAX_FILE_SIZE_MB: int = 25

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 30

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Retrieval
    VECTOR_CANDIDATES: int = 20
    KEYWORD_CANDIDATES: int = 20
    RRF_K: int = 60
    DEFAULT_TOP_K: int = 5

    # Embedding batching
    EMBEDDING_BATCH_SIZE: int = 32

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _validate_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
