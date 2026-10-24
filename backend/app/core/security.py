"""Password hashing, JWT issuance/verification, and API key generation.

API key format: "rag_<32 url-safe-base64 bytes>". We store only sha256(raw_key) plus the
first 8 characters of the key body as a display prefix; the raw key is returned to the
caller exactly once, at creation time, and is never persisted or logged.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.exceptions import UnauthorizedError

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

API_KEY_PREFIX = "rag_"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(password, password_hash)
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, expires_minutes: int | None = None) -> str:
    expiry = expires_minutes if expires_minutes is not None else settings.JWT_EXPIRY_MINUTES
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expiry),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token.") from exc


def generate_api_key() -> Tuple[str, str, str]:
    """Returns (full_key, key_hash, key_prefix)."""
    raw = secrets.token_urlsafe(32)
    full_key = f"{API_KEY_PREFIX}{raw}"
    key_hash = hash_api_key(full_key)
    key_prefix = full_key[: len(API_KEY_PREFIX) + 8]
    return full_key, key_hash, key_prefix


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def looks_like_api_key(token: str) -> bool:
    return token.startswith(API_KEY_PREFIX)
