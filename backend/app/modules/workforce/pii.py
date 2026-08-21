"""Envelope-style field encryption for sensitive Workforce identifiers."""

from __future__ import annotations

import base64
from hashlib import sha256
import hmac
import os
import secrets


_LOOKUP_CONTEXT = b"eay-workforce-tckn-lookup-v1"


def _decode_key(encoded: str, variable: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except Exception as error:
        raise RuntimeError(f"{variable} must be valid urlsafe base64") from error
    if len(key) != 32:
        raise RuntimeError(f"{variable} must be a base64 encoded 32-byte key")
    return key


def _key() -> bytes:
    encoded = os.getenv("OPEX_PII_KEY", "")
    if not encoded:
        raise RuntimeError("OPEX_PII_KEY is required for sensitive identity data")
    return _decode_key(encoded, "OPEX_PII_KEY")


def _lookup_key() -> bytes:
    encoded = os.getenv("OPEX_PII_LOOKUP_KEY", "")
    if encoded:
        return _decode_key(encoded, "OPEX_PII_LOOKUP_KEY")
    if os.getenv("DOCKOS_ENV", "development").strip().lower() == "production":
        raise RuntimeError("OPEX_PII_LOOKUP_KEY is required in production")
    # Local/test compatibility only. The encryption key is never used directly
    # as an HMAC key; domain separation derives an independent lookup key.
    return hmac.new(_key(), _LOOKUP_CONTEXT, sha256).digest()


def ensure_lookup_key_ready() -> None:
    _lookup_key()


def lookup_digest(value: str) -> str:
    normalized = "".join(character for character in str(value or "") if character.isdigit())
    if len(normalized) != 11:
        raise ValueError("TCKN lookup requires exactly 11 digits")
    digest = hmac.new(_lookup_key(), normalized.encode("ascii"), sha256).hexdigest()
    return f"v1:{digest}"


def lookup_matches(expected: str | None, value: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(str(expected), lookup_digest(value))


def encrypt(value: str, context: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode(), context.encode())
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(value: str, context: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.urlsafe_b64decode(value)
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], context.encode()).decode()
