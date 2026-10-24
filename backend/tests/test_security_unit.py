"""Pure-logic unit tests for app.core.security. No database or network required."""

from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    looks_like_api_key,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_jwt_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)


def test_jwt_invalid_token_raises() -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token("not.a.valid.jwt")


def test_generate_api_key_format_and_hash() -> None:
    full_key, key_hash, prefix = generate_api_key()
    assert full_key.startswith("rag_")
    assert prefix == full_key[:12]
    assert key_hash == hash_api_key(full_key)
    # Two generated keys must never collide.
    full_key_2, _, _ = generate_api_key()
    assert full_key != full_key_2


def test_looks_like_api_key() -> None:
    assert looks_like_api_key("rag_abc123")
    assert not looks_like_api_key("eyJhbGciOi.abc.def")
