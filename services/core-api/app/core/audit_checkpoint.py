"""Signed, externally anchorable checkpoints for the Jarvis audit hash chain.

A signed checkpoint proves which verified tenant chain tip Core observed and signed.
It is deliberately *not* an immutable-storage/WORM receipt. External immutable
storage and independent key custody remain separate production controls.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

AUDIT_CHECKPOINT_TYP = "eay-audit-checkpoint+jwt"
AUDIT_CHECKPOINT_SCHEMA = "eay.audit.checkpoint.v1"
AUDIT_CHECKPOINT_PURPOSE = "external-immutable-anchor"
AUDIT_CHAIN_ALGORITHM = "sha256:eay-audit-chain-v1"
AUDIT_CHAIN_SOURCE = "postgresql.public.audit_events"
GENESIS_HASH = "0" * 64
MAX_PRIVATE_KEY_BYTES = 64 * 1024
DEFAULT_PAGE_SIZE = 1000
KID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AuditCheckpointConfigurationError(RuntimeError):
    """Raised when signing or verification material is unsafe or unavailable."""


class AuditCheckpointValidationError(RuntimeError):
    """Raised when the audit chain or signed checkpoint cannot be trusted."""


@dataclass(frozen=True)
class AuditCheckpointSettings:
    environment: str
    issuer: str
    signing_key_file: str
    signing_kid: str

    @classmethod
    def from_environment(cls) -> "AuditCheckpointSettings":
        environment = os.getenv("OPEX_ENVIRONMENT", "development").strip()
        issuer = os.getenv(
            "OPEX_AUDIT_CHECKPOINT_ISSUER",
            "opex-core-audit-checkpoint",
        ).strip()
        signing_key_file = os.getenv(
            "OPEX_AUDIT_CHECKPOINT_SIGNING_KEY_FILE",
            "",
        ).strip()
        signing_kid = os.getenv(
            "OPEX_AUDIT_CHECKPOINT_SIGNING_KID",
            "",
        ).strip()

        if not issuer:
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint issuer is required"
            )
        if not signing_key_file:
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key file is required"
            )
        if not KID_PATTERN.fullmatch(signing_kid):
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key identifier is invalid"
            )
        if environment in {"staging", "production"} and os.getenv(
            "OPEX_AUDIT_CHECKPOINT_SIGNING_KEY",
            "",
        ).strip():
            raise AuditCheckpointConfigurationError(
                "Private audit checkpoint signing material must not be supplied "
                "through environment variables"
            )

        return cls(
            environment=environment,
            issuer=issuer,
            signing_key_file=signing_key_file,
            signing_kid=signing_kid,
        )


@dataclass(frozen=True)
class AuditChainTip:
    tenant_id: UUID
    chain_sequence: int
    event_hash: str
    event_count: int


def _audit_event_hash(sequence: int, previous_hash: str, payload: str) -> str:
    value = f"eay-audit-chain-v1|{sequence}|{previous_hash}|{payload}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_audit_chain_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    tenant_id: UUID,
    expected_start_sequence: int = 1,
    expected_previous_hash: str = GENESIS_HASH,
) -> AuditChainTip:
    """Verify a contiguous audit-chain segment and return its trusted tip."""
    if expected_start_sequence < 1:
        raise AuditCheckpointValidationError(
            "Audit chain start sequence must be positive"
        )
    if not HASH_PATTERN.fullmatch(expected_previous_hash):
        raise AuditCheckpointValidationError(
            "Audit chain previous hash is invalid"
        )
    if not rows:
        raise AuditCheckpointValidationError("Audit chain segment is empty")

    previous_hash = expected_previous_hash
    expected_sequence = expected_start_sequence
    for row in rows:
        try:
            row_tenant = UUID(str(row["tenant_id"]))
            sequence = int(row["chain_sequence"])
            stored_previous_hash = str(row["previous_event_hash"])
            event_hash = str(row["event_hash"])
            payload = str(row["event_payload"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditCheckpointValidationError(
                "Audit chain row is malformed"
            ) from exc

        if row_tenant != tenant_id:
            raise AuditCheckpointValidationError(
                "Audit chain row crosses tenant boundary"
            )
        if sequence != expected_sequence:
            raise AuditCheckpointValidationError(
                "Audit chain sequence is not contiguous"
            )
        if stored_previous_hash != previous_hash:
            raise AuditCheckpointValidationError(
                "Audit chain previous hash linkage is invalid"
            )
        if not HASH_PATTERN.fullmatch(event_hash):
            raise AuditCheckpointValidationError(
                "Audit chain event hash is invalid"
            )
        recomputed = _audit_event_hash(sequence, stored_previous_hash, payload)
        if event_hash != recomputed:
            raise AuditCheckpointValidationError(
                "Audit chain event hash does not match canonical payload"
            )

        previous_hash = event_hash
        expected_sequence += 1

    return AuditChainTip(
        tenant_id=tenant_id,
        chain_sequence=expected_sequence - 1,
        event_hash=previous_hash,
        event_count=len(rows),
    )


async def verify_tenant_audit_chain(
    connection: Any,
    *,
    tenant_id: UUID,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AuditChainTip:
    """Verify one tenant chain in a repeatable-read snapshot without cross-tenant data."""
    if not 1 <= page_size <= 10_000:
        raise ValueError("Audit checkpoint page size must be between 1 and 10000")

    next_sequence = 1
    previous_hash = GENESIS_HASH
    event_count = 0
    latest_tip: AuditChainTip | None = None

    async with connection.transaction(isolation="repeatable_read", readonly=True):
        while True:
            rows = await connection.fetch(
                """
                SELECT tenant_id, chain_sequence, previous_event_hash,
                       event_hash, event_payload
                FROM public.audit_events
                WHERE tenant_id = $1 AND chain_sequence >= $2
                ORDER BY chain_sequence
                LIMIT $3
                """,
                tenant_id,
                next_sequence,
                page_size,
            )
            if not rows:
                break

            segment_tip = verify_audit_chain_rows(
                rows,
                tenant_id=tenant_id,
                expected_start_sequence=next_sequence,
                expected_previous_hash=previous_hash,
            )
            event_count += len(rows)
            latest_tip = AuditChainTip(
                tenant_id=tenant_id,
                chain_sequence=segment_tip.chain_sequence,
                event_hash=segment_tip.event_hash,
                event_count=event_count,
            )
            next_sequence = segment_tip.chain_sequence + 1
            previous_hash = segment_tip.event_hash

            if len(rows) < page_size:
                break

    if latest_tip is None:
        raise AuditCheckpointValidationError(
            "Cannot sign an empty tenant audit chain"
        )
    if latest_tip.chain_sequence != latest_tip.event_count:
        raise AuditCheckpointValidationError(
            "Audit chain contains a sequence/count mismatch"
        )
    return latest_tip


class AuditCheckpointSigner:
    """Dedicated P-256 signer for archival audit checkpoints."""

    def __init__(self, settings: AuditCheckpointSettings) -> None:
        self.settings = settings
        self._private_key = self._load_private_key()

    def _load_private_key(self) -> ec.EllipticCurvePrivateKey:
        path = Path(self.settings.signing_key_file)
        try:
            stat = path.stat()
        except OSError as exc:
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key is unavailable"
            ) from exc

        if not path.is_file() or stat.st_size <= 0 or stat.st_size > MAX_PRIVATE_KEY_BYTES:
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key file is invalid"
            )
        if self.settings.environment in {"staging", "production"} and stat.st_mode & 0o077:
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key file permissions are too broad"
            )

        try:
            key = serialization.load_pem_private_key(
                path.read_bytes(),
                password=None,
            )
        except Exception as exc:
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key cannot be loaded"
            ) from exc

        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
            key.curve,
            ec.SECP256R1,
        ):
            raise AuditCheckpointConfigurationError(
                "Audit checkpoint signing key must be a P-256 EC private key"
            )
        return key

    def public_key_pem(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def issue_checkpoint(
        self,
        *,
        tip: AuditChainTip,
        issued_at: datetime | None = None,
    ) -> str:
        timestamp = issued_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Audit checkpoint issued_at must be timezone-aware")
        issued_epoch = int(timestamp.timestamp())
        payload = {
            "iss": self.settings.issuer,
            "sub": str(tip.tenant_id),
            "tenant_id": str(tip.tenant_id),
            "purpose": AUDIT_CHECKPOINT_PURPOSE,
            "schema": AUDIT_CHECKPOINT_SCHEMA,
            "source": AUDIT_CHAIN_SOURCE,
            "chain_algorithm": AUDIT_CHAIN_ALGORITHM,
            "chain_sequence": tip.chain_sequence,
            "event_count": tip.event_count,
            "event_hash": tip.event_hash,
            "checkpoint_id": str(uuid4()),
            "iat": issued_epoch,
            "anchor_state": "unanchored_signed_checkpoint",
            "immutable_storage_receipt": False,
        }
        return jwt.encode(
            payload,
            self._private_key,
            algorithm="ES256",
            headers={
                "kid": self.settings.signing_kid,
                "typ": AUDIT_CHECKPOINT_TYP,
            },
        )


async def issue_tenant_audit_checkpoint(
    connection: Any,
    *,
    tenant_id: UUID,
    signer: AuditCheckpointSigner,
    page_size: int = DEFAULT_PAGE_SIZE,
    issued_at: datetime | None = None,
) -> str:
    tip = await verify_tenant_audit_chain(
        connection,
        tenant_id=tenant_id,
        page_size=page_size,
    )
    return signer.issue_checkpoint(tip=tip, issued_at=issued_at)


def verify_signed_audit_checkpoint(
    token: str,
    *,
    public_key_pem: bytes,
    expected_issuer: str,
    expected_tenant_id: UUID,
    expected_kid: str,
) -> dict[str, Any]:
    """Verify a checkpoint signature and its anti-false-proof truth boundary."""
    if not expected_issuer.strip():
        raise ValueError("Expected audit checkpoint issuer is required")
    if not KID_PATTERN.fullmatch(expected_kid):
        raise ValueError("Expected audit checkpoint key identifier is invalid")

    try:
        public_key = serialization.load_pem_public_key(public_key_pem)
    except Exception as exc:
        raise AuditCheckpointValidationError(
            "Audit checkpoint public key cannot be loaded"
        ) from exc
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
        public_key.curve,
        ec.SECP256R1,
    ):
        raise AuditCheckpointValidationError(
            "Audit checkpoint public key must be P-256"
        )

    try:
        header = jwt.get_unverified_header(token)
        if header.get("typ") != AUDIT_CHECKPOINT_TYP:
            raise AuditCheckpointValidationError(
                "Audit checkpoint token type is invalid"
            )
        if header.get("kid") != expected_kid:
            raise AuditCheckpointValidationError(
                "Audit checkpoint key identifier is unexpected"
            )
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            issuer=expected_issuer,
            options={
                "require": [
                    "iss",
                    "sub",
                    "tenant_id",
                    "purpose",
                    "schema",
                    "source",
                    "chain_algorithm",
                    "chain_sequence",
                    "event_count",
                    "event_hash",
                    "checkpoint_id",
                    "iat",
                    "anchor_state",
                    "immutable_storage_receipt",
                ]
            },
        )
    except AuditCheckpointValidationError:
        raise
    except jwt.InvalidTokenError as exc:
        raise AuditCheckpointValidationError(
            "Audit checkpoint signature or claims are invalid"
        ) from exc

    tenant_text = str(expected_tenant_id)
    if claims.get("sub") != tenant_text or claims.get("tenant_id") != tenant_text:
        raise AuditCheckpointValidationError(
            "Audit checkpoint tenant boundary is invalid"
        )
    if claims.get("purpose") != AUDIT_CHECKPOINT_PURPOSE:
        raise AuditCheckpointValidationError(
            "Audit checkpoint purpose is invalid"
        )
    if claims.get("schema") != AUDIT_CHECKPOINT_SCHEMA:
        raise AuditCheckpointValidationError(
            "Audit checkpoint schema is invalid"
        )
    if claims.get("source") != AUDIT_CHAIN_SOURCE:
        raise AuditCheckpointValidationError(
            "Audit checkpoint source is invalid"
        )
    if claims.get("chain_algorithm") != AUDIT_CHAIN_ALGORITHM:
        raise AuditCheckpointValidationError(
            "Audit checkpoint chain algorithm is invalid"
        )
    if claims.get("anchor_state") != "unanchored_signed_checkpoint":
        raise AuditCheckpointValidationError(
            "Audit checkpoint anchor state is invalid"
        )
    if claims.get("immutable_storage_receipt") is not False:
        raise AuditCheckpointValidationError(
            "Signed checkpoint must not claim immutable storage receipt"
        )

    sequence = claims.get("chain_sequence")
    event_count = claims.get("event_count")
    event_hash = claims.get("event_hash")
    if not isinstance(sequence, int) or sequence <= 0:
        raise AuditCheckpointValidationError(
            "Audit checkpoint chain sequence is invalid"
        )
    if event_count != sequence:
        raise AuditCheckpointValidationError(
            "Audit checkpoint event count does not match chain sequence"
        )
    if not isinstance(event_hash, str) or not HASH_PATTERN.fullmatch(event_hash):
        raise AuditCheckpointValidationError(
            "Audit checkpoint event hash is invalid"
        )
    try:
        UUID(str(claims.get("checkpoint_id")))
    except ValueError as exc:
        raise AuditCheckpointValidationError(
            "Audit checkpoint identifier is invalid"
        ) from exc

    return claims
