from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app.cyber_championship_signature_guard as signature_guard
from app.cyber_championship_signature_guard import (
    DetachedSignatureEnvelope,
    SignerRole,
    TrustedSigner,
    TrustedSignerPolicy,
    assess_signature_chain,
    verify_detached_signature,
)

NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


def _key_material() -> tuple[Ed25519PrivateKey, str, bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, hashlib.sha256(der).hexdigest(), pem


def _prepare_trust_root(
    trust_dir: Path,
) -> dict[SignerRole, tuple[Ed25519PrivateKey, str, str]]:
    (trust_dir / "keys").mkdir(parents=True)
    materials: dict[SignerRole, tuple[Ed25519PrivateKey, str, str]] = {}
    signers: list[TrustedSigner] = []
    for role in SignerRole:
        private_key, fingerprint, pem = _key_material()
        key_id = f"{role.value}-2026-08"
        (trust_dir / "keys" / f"{key_id}.pem").write_bytes(pem)
        materials[role] = (private_key, key_id, fingerprint)
        signers.append(
            TrustedSigner(
                role=role,
                key_id=key_id,
                public_key_fingerprint=fingerprint,
            )
        )
    policy = TrustedSignerPolicy(signers=tuple(signers))
    (trust_dir / "trusted_signers.json").write_text(
        json.dumps(policy.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    return materials


def _write_signed_subject(
    *,
    evidence_dir: Path,
    subject_name: str,
    role: SignerRole,
    material: tuple[Ed25519PrivateKey, str, str],
) -> None:
    private_key, key_id, fingerprint = material
    subject_bytes = json.dumps(
        {"subject": subject_name, "fixture": "sealed-metadata-only"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (evidence_dir / subject_name).write_bytes(subject_bytes)
    values = {
        "contract": signature_guard.SIGNATURE_CONTRACT,
        "subject_file": subject_name,
        "subject_sha256": hashlib.sha256(subject_bytes).hexdigest(),
        "signer_role": role,
        "key_id": key_id,
        "public_key_fingerprint": fingerprint,
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(hours=1),
    }
    placeholder = DetachedSignatureEnvelope(
        **values,
        signature_b64=base64.b64encode(b"0" * 64).decode("ascii"),
    )
    signature = private_key.sign(signature_guard._signature_payload(placeholder))
    envelope = DetachedSignatureEnvelope(
        **values,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )
    envelope_name = signature_guard._signature_file_name(subject_name)
    (evidence_dir / envelope_name).write_text(
        json.dumps(envelope.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )


def _prepare_complete_chain(
    root: Path,
) -> tuple[Path, Path, dict[SignerRole, tuple[Ed25519PrivateKey, str, str]]]:
    evidence_dir = root / "evidence"
    trust_dir = root / "trust"
    evidence_dir.mkdir()
    materials = _prepare_trust_root(trust_dir)
    for subject_name, role in signature_guard._REQUIRED_SUBJECTS.items():
        _write_signed_subject(
            evidence_dir=evidence_dir,
            subject_name=subject_name,
            role=role,
            material=materials[role],
        )
    return evidence_dir, trust_dir, materials


def test_complete_detached_signature_chain_verifies() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as raw:
        evidence_dir, trust_dir, _ = _prepare_complete_chain(Path(raw))
        report = assess_signature_chain(
            evidence_dir=evidence_dir,
            trust_dir=trust_dir,
            now=NOW,
        )
    assert report["status"] == "verified"
    assert report["verified_subject_count"] == report["required_subject_count"]
    assert report["raw_receipt_contents_printed"] is False
    assert report["raw_keys_or_signatures_printed"] is False
    assert report["secrets_or_ground_truth_printed"] is False


def test_tampered_receipt_fails_cryptographic_chain(tmp_path: Path) -> None:
    evidence_dir, trust_dir, _ = _prepare_complete_chain(tmp_path)
    (evidence_dir / "sealed_bank.json").write_text(
        '{"subject":"sealed_bank.json","tampered":true}',
        encoding="utf-8",
    )
    report = assess_signature_chain(
        evidence_dir=evidence_dir,
        trust_dir=trust_dir,
        now=NOW,
    )
    assert report["status"] == "blocked"
    assert "signature_verification_failed:sealed_bank.json" in report["blockers"]


def test_wrong_signer_role_is_rejected_even_with_valid_signature(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    trust_dir = tmp_path / "trust"
    evidence_dir.mkdir()
    materials = _prepare_trust_root(trust_dir)
    _write_signed_subject(
        evidence_dir=evidence_dir,
        subject_name="sealed_bank.json",
        role=SignerRole.EAY_SECURITY_GUARDIAN,
        material=materials[SignerRole.EAY_SECURITY_GUARDIAN],
    )
    try:
        verify_detached_signature(
            subject_path=evidence_dir / "sealed_bank.json",
            envelope_path=evidence_dir / "sealed_bank.signature.json",
            trust_dir=trust_dir,
            expected_role=SignerRole.INDEPENDENT_EVALUATOR,
            now=NOW,
        )
    except ValueError as exc:
        assert str(exc) == "signature_signer_role_mismatch"
    else:
        raise AssertionError("wrong signer role unexpectedly verified")


def test_expired_signature_is_rejected(tmp_path: Path) -> None:
    evidence_dir, trust_dir, _ = _prepare_complete_chain(tmp_path)
    report = assess_signature_chain(
        evidence_dir=evidence_dir,
        trust_dir=trust_dir,
        now=NOW + timedelta(days=1),
    )
    assert report["status"] == "blocked"
    assert report["verified_subject_count"] == 0


def test_authorized_workflow_orders_signature_scope_and_external_gates() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github/workflows/jarvis-cyber-championship-run.yml"
    ).read_text(encoding="utf-8")
    signature = "python -m app.cyber_championship_signature_guard"
    scope = "python -m app.cyber_championship_tenant_scope_guard"
    external = "python scripts/run_cyber_championship_external_preflight.py"
    assert signature in workflow
    assert scope in workflow
    assert external in workflow
    assert workflow.index(signature) < workflow.index(scope) < workflow.index(external)
    assert "EAY_CHAMPIONSHIP_TRUST_DIR" in workflow
    assert "secrets." not in workflow
