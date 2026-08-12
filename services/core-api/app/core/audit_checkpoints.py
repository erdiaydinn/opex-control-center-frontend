"""Cryptographic audit checkpoints designed for an external signing boundary.

This module intentionally contains no private-key loading or generation. The
caller supplies a signing callback, which production can back with KMS/HSM.
Verification uses public P-256 JWKS material only.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from pydantic import BaseModel, ConfigDict, Field

CHECKPOINT_VERSION = 1
CHECKPOINT_ALGORITHM = "ES256"
CHECKPOINT_DOMAIN = "eay-audit-checkpoint-v1"
CHECKPOINT_GENESIS_HASH = "0" * 64
MAX_JWKS_KEYS = 16
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class AuditCheckpointError(ValueError):
    """Base fail-closed checkpoint contract error."""


class AuditCheckpointInvalid(AuditCheckpointError):
    """Checkpoint structure, hash or signature is invalid."""


class AuditCheckpointKeyUnavailable(AuditCheckpointError):
    """The required public verification key is unavailable or ambiguous."""


class AuditCheckpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = CHECKPOINT_VERSION
    checkpoint_id: UUID
    tenant_id: UUID
    chain_sequence: int = Field(ge=1)
    event_hash: str = Field(pattern=SHA256_PATTERN)
    previous_checkpoint_hash: str = Field(pattern=SHA256_PATTERN)
    captured_at: datetime
    signing_key_id: str = Field(min_length=8, max_length=128)
    algorithm: Literal["ES256"] = CHECKPOINT_ALGORITHM


class SignedAuditCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: AuditCheckpointPayload
    checkpoint_hash: str = Field(pattern=SHA256_PATTERN)
    signature: str = Field(min_length=80, max_length=128)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AuditCheckpointInvalid("Checkpoint base64url value is invalid")
    try:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise AuditCheckpointInvalid("Checkpoint base64url value is invalid") from exc


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuditCheckpointInvalid("Checkpoint captured_at must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_checkpoint_payload(payload: AuditCheckpointPayload) -> bytes:
    canonical = {
        "algorithm": payload.algorithm,
        "captured_at_utc": _utc_timestamp(payload.captured_at),
        "chain_sequence": payload.chain_sequence,
        "checkpoint_id": str(payload.checkpoint_id),
        "event_hash": payload.event_hash,
        "previous_checkpoint_hash": payload.previous_checkpoint_hash,
        "signing_key_id": payload.signing_key_id,
        "tenant_id": str(payload.tenant_id),
        "version": payload.version,
    }
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def compute_checkpoint_hash(payload: AuditCheckpointPayload) -> str:
    material = CHECKPOINT_DOMAIN.encode("ascii") + b"|" + canonical_checkpoint_payload(payload)
    return hashlib.sha256(material).hexdigest()


def checkpoint_signing_message(payload: AuditCheckpointPayload) -> bytes:
    checkpoint_hash = compute_checkpoint_hash(payload)
    return f"{CHECKPOINT_DOMAIN}|{checkpoint_hash}".encode("ascii")


def create_signed_checkpoint(
    payload: AuditCheckpointPayload,
    *,
    sign_es256: Callable[[bytes, str], bytes],
) -> SignedAuditCheckpoint:
    if not callable(sign_es256):
        raise AuditCheckpointInvalid("Checkpoint signer is invalid")

    message = checkpoint_signing_message(payload)
    signature = sign_es256(message, payload.signing_key_id)
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise AuditCheckpointInvalid("Checkpoint signer must return raw 64-byte ES256")

    return SignedAuditCheckpoint(
        payload=payload,
        checkpoint_hash=compute_checkpoint_hash(payload),
        signature=_b64url_encode(signature),
    )


def _public_key_from_jwk(jwk: Mapping[str, Any]) -> ec.EllipticCurvePublicKey:
    if not isinstance(jwk, Mapping):
        raise AuditCheckpointKeyUnavailable("Checkpoint JWK is invalid")
    if "d" in jwk:
        raise AuditCheckpointKeyUnavailable("Checkpoint JWKS must not contain private key data")
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise AuditCheckpointKeyUnavailable("Checkpoint JWK curve is unsupported")
    if jwk.get("use") not in {None, "sig"}:
        raise AuditCheckpointKeyUnavailable("Checkpoint JWK use is invalid")
    if jwk.get("alg") not in {None, CHECKPOINT_ALGORITHM}:
        raise AuditCheckpointKeyUnavailable("Checkpoint JWK algorithm is invalid")

    x = _b64url_decode(str(jwk.get("x", "")))
    y = _b64url_decode(str(jwk.get("y", "")))
    if len(x) != 32 or len(y) != 32:
        raise AuditCheckpointKeyUnavailable("Checkpoint JWK coordinates are invalid")

    try:
        numbers = ec.EllipticCurvePublicNumbers(
            int.from_bytes(x, "big"),
            int.from_bytes(y, "big"),
            ec.SECP256R1(),
        )
        return numbers.public_key()
    except ValueError as exc:
        raise AuditCheckpointKeyUnavailable("Checkpoint JWK point is invalid") from exc


def _select_jwk(jwks: Mapping[str, Any], *, key_id: str) -> Mapping[str, Any]:
    if not isinstance(jwks, Mapping):
        raise AuditCheckpointKeyUnavailable("Checkpoint JWKS is invalid")
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_JWKS_KEYS:
        raise AuditCheckpointKeyUnavailable("Checkpoint JWKS key set is invalid")

    matches = [
        key
        for key in keys
        if isinstance(key, Mapping) and key.get("kid") == key_id
    ]
    if len(matches) != 1:
        raise AuditCheckpointKeyUnavailable("Checkpoint signing key is unavailable or ambiguous")
    return matches[0]


def verify_signed_checkpoint(
    checkpoint: SignedAuditCheckpoint,
    *,
    jwks: Mapping[str, Any],
) -> None:
    expected_hash = compute_checkpoint_hash(checkpoint.payload)
    if checkpoint.checkpoint_hash != expected_hash:
        raise AuditCheckpointInvalid("Checkpoint hash mismatch")

    signature = _b64url_decode(checkpoint.signature)
    if len(signature) != 64:
        raise AuditCheckpointInvalid("Checkpoint signature length is invalid")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if r == 0 or s == 0:
        raise AuditCheckpointInvalid("Checkpoint signature scalar is invalid")

    jwk = _select_jwk(jwks, key_id=checkpoint.payload.signing_key_id)
    public_key = _public_key_from_jwk(jwk)
    der_signature = utils.encode_dss_signature(r, s)

    try:
        public_key.verify(
            der_signature,
            checkpoint_signing_message(checkpoint.payload),
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature as exc:
        raise AuditCheckpointInvalid("Checkpoint signature verification failed") from exc


def verify_checkpoint_chain(
    checkpoints: Sequence[SignedAuditCheckpoint],
    *,
    jwks: Mapping[str, Any],
    tenant_id: UUID | None = None,
) -> str:
    if not checkpoints:
        raise AuditCheckpointInvalid("Checkpoint chain is empty")

    expected_tenant = tenant_id
    previous_checkpoint_hash = CHECKPOINT_GENESIS_HASH
    previous_event_sequence = 0
    previous_captured_at: datetime | None = None

    for checkpoint in checkpoints:
        verify_signed_checkpoint(checkpoint, jwks=jwks)
        payload = checkpoint.payload

        if expected_tenant is None:
            expected_tenant = payload.tenant_id
        if payload.tenant_id != expected_tenant:
            raise AuditCheckpointInvalid("Checkpoint chain crosses tenant boundary")
        if payload.previous_checkpoint_hash != previous_checkpoint_hash:
            raise AuditCheckpointInvalid("Checkpoint chain link is broken")
        if payload.chain_sequence <= previous_event_sequence:
            raise AuditCheckpointInvalid("Checkpoint event sequence must increase")
        if previous_captured_at is not None and payload.captured_at <= previous_captured_at:
            raise AuditCheckpointInvalid("Checkpoint capture time must increase")

        previous_checkpoint_hash = checkpoint.checkpoint_hash
        previous_event_sequence = payload.chain_sequence
        previous_captured_at = payload.captured_at

    return previous_checkpoint_hash
