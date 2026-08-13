"""Envelope-style field encryption for sensitive Workforce identifiers."""

from __future__ import annotations

import base64
import os
import secrets


def _key() -> bytes:
    encoded = os.getenv("OPEX_PII_KEY", "")
    if not encoded:
        raise RuntimeError("OPEX_PII_KEY is required for sensitive identity data")
    key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    if len(key) != 32:
        raise RuntimeError("OPEX_PII_KEY must be a base64 encoded 32-byte key")
    return key


def encrypt(value: str, context: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode(), context.encode())
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(value: str, context: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.urlsafe_b64decode(value)
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], context.encode()).decode()
