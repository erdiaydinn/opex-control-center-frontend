"""Cryptographic trust guard for externally supplied championship receipts.

Every receipt consumed by the authorized championship workflow must have a
detached Ed25519 signature whose signer is allowlisted by a trust policy mounted
from the protected self-hosted runner. Evidence and trust roots remain separate.
The guard never prints receipt contents, public-key material, signatures, secrets
or sealed ground truth.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

SIGNATURE_CONTRACT = "eay-cyber-championship-detached-signature-v1"
_TRUST_POLICY_CONTRACT = "eay-cyber-championship-trusted-signers-v1"
_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SUBJECT_FILE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}\.json$")


class SignerRole(str, Enum):
    INDEPENDENT_EVALUATOR = "independent_evaluator"
    EAY_SECURITY_GUARDIAN = "eay_security_guardian"
    VENDOR_OWNER = "vendor_owner"


_REQUIRED_SUBJECTS: dict[str, SignerRole] = {
    "sealed_bank.json": SignerRole.INDEPENDENT_EVALUATOR,
    "sandbox_authorization.json": SignerRole.EAY_SECURITY_GUARDIAN,
    "evaluator_authority.json": SignerRole.INDEPENDENT_EVALUATOR,
    "evaluator_trust_policy.json": SignerRole.EAY_SECURITY_GUARDIAN,
    "crowdstrike_runner_authorization.json": SignerRole.VENDOR_OWNER,
    "crowdstrike_credential_binding.json": SignerRole.EAY_SECURITY_GUARDIAN,
    "google_runner_authorization.json": SignerRole.VENDOR_OWNER,
    "google_credential_binding.json": SignerRole.EAY_SECURITY_GUARDIAN,
    "microsoft_runner_authorization.json": SignerRole.VENDOR_OWNER,
    "microsoft_credential_binding.json": SignerRole.EAY_SECURITY_GUARDIAN,
}


class TrustedSigner(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: SignerRole
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    public_key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class TrustedSignerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = _TRUST_POLICY_CONTRACT
    signers: tuple[TrustedSigner, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def policy_is_unambiguous(self) -> TrustedSignerPolicy:
        identities = {(item.role, item.key_id) for item in self.signers}
        if len(identities) != len(self.signers):
            raise ValueError("signature_trust_policy_duplicate_signer")
        if {item.role for item in self.signers} != set(SignerRole):
            raise ValueError("signature_trust_policy_missing_required_role")
        return self


class DetachedSignatureEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = SIGNATURE_CONTRACT
    subject_file: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}\.json$")
    subject_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signer_role: SignerRole
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    public_key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: datetime
    expires_at: datetime
    signature_b64: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def envelope_is_well_formed(self) -> DetachedSignatureEnvelope:
        _aware(self.issued_at, "signature_issued_at_requires_timezone")
        _aware(self.expires_at, "signature_expires_at_requires_timezone")
        if self.expires_at <= self.issued_at:
            raise ValueError("signature_expiry_invalid")
        if not _KEY_ID.fullmatch(self.key_id) or not _SUBJECT_FILE.fullmatch(self.subject_file):
            raise ValueError("signature_identifier_invalid")
        try:
            decoded = base64.b64decode(self.signature_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("signature_encoding_invalid") from exc
        if len(decoded) != 64:
            raise ValueError("signature_length_invalid")
        return self


class SignatureVerificationStatus(str, Enum):
    VERIFIED = "verified"
    BLOCKED = "blocked"


class DetachedSignatureVerificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = SIGNATURE_CONTRACT
    subject_file: str
    subject_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signer_role: SignerRole
    key_id: str
    public_key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_at: datetime
    status: SignatureVerificationStatus
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_verified(self) -> DetachedSignatureVerificationReceipt:
        _aware(self.verified_at, "signature_verified_at_requires_timezone")
        if self.status is not SignatureVerificationStatus.VERIFIED:
            raise ValueError("signature_verification_receipt_not_verified")
        _verify_fingerprint(self, "signature_verification_fingerprint_mismatch")
        return self


def verify_detached_signature(
    *,
    subject_path: Path,
    envelope_path: Path,
    trust_dir: Path,
    expected_role: SignerRole,
    now: datetime,
) -> DetachedSignatureVerificationReceipt:
    _aware(now, "signature_verification_time_requires_timezone")
    subject_name = subject_path.name
    if subject_name != subject_path.name or not _SUBJECT_FILE.fullmatch(subject_name):
        raise ValueError("signature_subject_file_invalid")
    envelope = DetachedSignatureEnvelope.model_validate(_load_json(envelope_path))
    if envelope.subject_file != subject_name:
        raise ValueError("signature_subject_name_mismatch")
    if envelope.signer_role is not expected_role:
        raise ValueError("signature_signer_role_mismatch")
    if now < envelope.issued_at or now >= envelope.expires_at:
        raise ValueError("signature_not_current")

    subject_bytes = subject_path.read_bytes()
    subject_sha256 = hashlib.sha256(subject_bytes).hexdigest()
    if subject_sha256 != envelope.subject_sha256:
        raise ValueError("signature_subject_digest_mismatch")

    policy = TrustedSignerPolicy.model_validate(
        _load_json(trust_dir / "trusted_signers.json")
    )
    trusted = next(
        (
            item
            for item in policy.signers
            if item.role is envelope.signer_role and item.key_id == envelope.key_id
        ),
        None,
    )
    if trusted is None:
        raise ValueError("signature_signer_not_trusted")
    if trusted.public_key_fingerprint != envelope.public_key_fingerprint:
        raise ValueError("signature_trust_fingerprint_mismatch")

    public_key = _load_public_key(trust_dir=trust_dir, key_id=envelope.key_id)
    actual_key_fingerprint = _public_key_fingerprint(public_key)
    if actual_key_fingerprint != envelope.public_key_fingerprint:
        raise ValueError("signature_public_key_fingerprint_mismatch")

    try:
        signature = base64.b64decode(envelope.signature_b64, validate=True)
        public_key.verify(signature, _signature_payload(envelope))
    except (InvalidSignature, binascii.Error, ValueError) as exc:
        raise ValueError("signature_cryptographic_verification_failed") from exc

    return _seal_model(
        DetachedSignatureVerificationReceipt,
        {
            "contract": SIGNATURE_CONTRACT,
            "subject_file": envelope.subject_file,
            "subject_sha256": envelope.subject_sha256,
            "signer_role": envelope.signer_role,
            "key_id": envelope.key_id,
            "public_key_fingerprint": envelope.public_key_fingerprint,
            "verified_at": now,
            "status": SignatureVerificationStatus.VERIFIED,
        },
    )


def assess_signature_chain(
    *,
    evidence_dir: Path,
    trust_dir: Path,
    now: datetime,
) -> dict[str, object]:
    blockers: list[str] = []
    receipts: list[DetachedSignatureVerificationReceipt] = []
    if not evidence_dir.is_dir():
        blockers.append("signature_evidence_directory_missing")
    if not trust_dir.is_dir():
        blockers.append("signature_trust_directory_missing")
    if blockers:
        return _report(blockers=blockers, receipts=receipts)

    for subject_name, role in _REQUIRED_SUBJECTS.items():
        subject_path = evidence_dir / subject_name
        envelope_path = evidence_dir / _signature_file_name(subject_name)
        if not subject_path.is_file():
            blockers.append(f"signature_subject_missing:{subject_name}")
            continue
        if not envelope_path.is_file():
            blockers.append(f"signature_envelope_missing:{subject_name}")
            continue
        try:
            receipt = verify_detached_signature(
                subject_path=subject_path,
                envelope_path=envelope_path,
                trust_dir=trust_dir,
                expected_role=role,
                now=now,
            )
        except (KeyError, OSError, TypeError, ValueError):
            blockers.append(f"signature_verification_failed:{subject_name}")
            continue
        receipts.append(receipt)

    if len(receipts) != len(_REQUIRED_SUBJECTS):
        blockers.append("signature_required_receipts_incomplete")
    return _report(blockers=blockers, receipts=receipts)


def _signature_file_name(subject_name: str) -> str:
    if not subject_name.endswith(".json"):
        raise ValueError("signature_subject_extension_invalid")
    return f"{subject_name[:-5]}.signature.json"


def _signature_payload(envelope: DetachedSignatureEnvelope) -> bytes:
    payload = envelope.model_dump(mode="json", exclude={"signature_b64"})
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return canonical.encode("utf-8")


def _load_public_key(*, trust_dir: Path, key_id: str) -> Ed25519PublicKey:
    if not _KEY_ID.fullmatch(key_id):
        raise ValueError("signature_key_id_invalid")
    root = trust_dir.resolve()
    key_path = (root / "keys" / f"{key_id}.pem").resolve()
    if root not in key_path.parents:
        raise ValueError("signature_key_path_escape")
    data = key_path.read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("signature_key_algorithm_not_ed25519")
    return key


def _public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    data = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError("signature_document_must_be_json_object")
    return value


def _report(
    *,
    blockers: list[str],
    receipts: list[DetachedSignatureVerificationReceipt],
) -> dict[str, object]:
    unique_blockers = tuple(dict.fromkeys(blockers))
    return {
        "status": "blocked" if unique_blockers else "verified",
        "blockers": unique_blockers,
        "verification_fingerprints": tuple(sorted(item.fingerprint for item in receipts)),
        "verified_subject_count": len(receipts),
        "required_subject_count": len(_REQUIRED_SUBJECTS),
        "raw_receipt_contents_printed": False,
        "raw_keys_or_signatures_printed": False,
        "secrets_or_ground_truth_printed": False,
    }


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _model_payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _verify_fingerprint(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_model_payload(model)):
        raise ValueError(error)


def _seal_model(model_cls: type[BaseModel], values: dict[str, Any]):
    draft = model_cls.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_cls.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--trust-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = assess_signature_chain(
        evidence_dir=args.evidence_dir,
        trust_dir=args.trust_dir,
        now=datetime.now(UTC),
    )
    print(json.dumps(report, sort_keys=True))
    if args.strict and report["status"] != "verified":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
