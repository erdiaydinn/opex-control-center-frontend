"""Cryptographic trust boundary for candidate-document scanner receipts.

The scanner callback is untrusted until this module has verified a signature over
the canonical, exact-evidence payload and atomically claimed its replay key.
Persistence implementations must back ``ReplayAuthority.claim`` with a unique
tenant/provider/receipt constraint in the same transaction that records the
receipt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import re
from typing import Callable, Protocol


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$")
_RESULTS = frozenset({"CLEAN", "INFECTED", "ERROR"})


class ScannerReceiptError(ValueError):
    """A scanner receipt failed closed at the cryptographic boundary."""


class ReplayAuthority(Protocol):
    def claim(self, tenant_id: str, provider: str, receipt_id: str) -> bool:
        """Atomically claim a receipt; return False if it was already claimed."""


SignatureVerifier = Callable[[str, bytes, bytes], bool]


@dataclass(frozen=True, slots=True)
class ScannerReceipt:
    tenant_id: str
    candidate_id: str
    evidence_id: str
    evidence_sha256: str
    provider: str
    engine: str
    key_id: str
    receipt_id: str
    nonce: str
    result: str
    issued_at: str

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def hmac_sha256_verifier(key_resolver: Callable[[str], bytes | None]) -> SignatureVerifier:
    """Build a constant-time HMAC verifier; resolver secrets stay outside payloads."""

    def verify(key_id: str, message: bytes, signature: bytes) -> bool:
        key = key_resolver(key_id)
        if not isinstance(key, bytes) or len(key) < 32:
            return False
        expected = hmac.new(key, message, hashlib.sha256).digest()
        return hmac.compare_digest(expected, signature)

    return verify


def _decode_signature(value: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ScannerReceiptError("scanner signature is missing or malformed")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ScannerReceiptError("scanner signature is malformed") from exc


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ScannerReceiptError("scanner issued_at is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScannerReceiptError("scanner issued_at is malformed") from exc
    if parsed.tzinfo is None:
        raise ScannerReceiptError("scanner issued_at must include timezone")
    return parsed.astimezone(UTC)


def verify_scanner_receipt(
    payload: dict,
    signature: str,
    *,
    verifier: SignatureVerifier,
    replay_authority: ReplayAuthority,
    expected_tenant_id: str,
    expected_candidate_id: str,
    expected_evidence_id: str,
    expected_evidence_sha256: str,
    now: datetime | None = None,
    max_age: timedelta = timedelta(minutes=5),
    max_future_skew: timedelta = timedelta(seconds=30),
) -> ScannerReceipt:
    """Verify binding, freshness, signature and replay status, in that order."""
    if not isinstance(payload, dict):
        raise ScannerReceiptError("scanner payload must be an object")
    required = set(ScannerReceipt.__dataclass_fields__)
    if set(payload) != required or not all(isinstance(payload[k], str) for k in required):
        raise ScannerReceiptError("scanner payload has an invalid contract")
    receipt = ScannerReceipt(**payload)
    identifiers = (
        receipt.tenant_id, receipt.candidate_id, receipt.evidence_id, receipt.provider,
        receipt.engine, receipt.key_id, receipt.receipt_id, receipt.nonce,
    )
    if not all(_IDENTIFIER.fullmatch(value) for value in identifiers):
        raise ScannerReceiptError("scanner payload contains an invalid identifier")
    if not _SHA256.fullmatch(receipt.evidence_sha256):
        raise ScannerReceiptError("scanner evidence hash is malformed")
    if receipt.result not in _RESULTS:
        raise ScannerReceiptError("scanner result is unsupported")
    expected = (expected_tenant_id, expected_candidate_id, expected_evidence_id, expected_evidence_sha256)
    actual = (receipt.tenant_id, receipt.candidate_id, receipt.evidence_id, receipt.evidence_sha256)
    if actual != expected:
        raise ScannerReceiptError("scanner receipt is not bound to the exact evidence")
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    issued = _parse_timestamp(receipt.issued_at)
    if issued > observed + max_future_skew or observed - issued > max_age:
        raise ScannerReceiptError("scanner receipt is outside its freshness window")
    raw_signature = _decode_signature(signature)
    if len(raw_signature) != hashlib.sha256().digest_size:
        raise ScannerReceiptError("scanner signature is malformed")
    if not verifier(receipt.key_id, receipt.canonical_bytes(), raw_signature):
        raise ScannerReceiptError("scanner signature verification failed")
    if not replay_authority.claim(receipt.tenant_id, receipt.provider, receipt.receipt_id):
        raise ScannerReceiptError("scanner receipt replay detected")
    return receipt
