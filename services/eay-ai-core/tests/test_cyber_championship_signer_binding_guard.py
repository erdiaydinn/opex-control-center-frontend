from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import app.cyber_championship_signature_guard as signature_guard
import app.cyber_championship_signer_binding_guard as binding_guard
from app.cyber_championship_signature_guard import (
    DetachedSignatureEnvelope,
    SignerRole,
    TrustedSigner,
    TrustedSignerPolicy,
)
from app.cyber_championship_signer_binding_guard import (
    SubjectSignerBinding,
    SubjectSignerBindingPolicy,
    assess_subject_signer_bindings,
)

NOW = datetime(2026, 8, 22, 17, 0, tzinfo=UTC)
_SIGNATURE = base64.b64encode(b"x" * 64).decode("ascii")
_KEYS = {
    "evaluator": "evaluator-key-2026-08",
    "security": "security-guardian-key-2026-08",
    "crowdstrike": "crowdstrike-owner-key-2026-08",
    "google": "google-owner-key-2026-08",
    "microsoft": "microsoft-owner-key-2026-08",
}


def _key_for_subject(subject: str) -> str:
    if subject in {"sealed_bank.json", "evaluator_authority.json"}:
        return _KEYS["evaluator"]
    if subject == "crowdstrike_runner_authorization.json":
        return _KEYS["crowdstrike"]
    if subject == "google_runner_authorization.json":
        return _KEYS["google"]
    if subject == "microsoft_runner_authorization.json":
        return _KEYS["microsoft"]
    return _KEYS["security"]


def _write_fixture(root: Path) -> tuple[Path, Path]:
    evidence = root / "evidence"
    trust = root / "trust"
    evidence.mkdir()
    trust.mkdir()
    signers = (
        TrustedSigner(role=SignerRole.INDEPENDENT_EVALUATOR, key_id=_KEYS["evaluator"], public_key_fingerprint="1" * 64),
        TrustedSigner(role=SignerRole.EAY_SECURITY_GUARDIAN, key_id=_KEYS["security"], public_key_fingerprint="2" * 64),
        TrustedSigner(role=SignerRole.VENDOR_OWNER, key_id=_KEYS["crowdstrike"], public_key_fingerprint="3" * 64),
        TrustedSigner(role=SignerRole.VENDOR_OWNER, key_id=_KEYS["google"], public_key_fingerprint="4" * 64),
        TrustedSigner(role=SignerRole.VENDOR_OWNER, key_id=_KEYS["microsoft"], public_key_fingerprint="5" * 64),
    )
    trusted = TrustedSignerPolicy(signers=signers)
    (trust / "trusted_signers.json").write_text(json.dumps(trusted.model_dump(mode="json")), encoding="utf-8")

    bindings = tuple(
        SubjectSignerBinding(
            subject_file=subject,
            signer_role=role,
            key_id=_key_for_subject(subject),
        )
        for subject, role in signature_guard._REQUIRED_SUBJECTS.items()
    )
    policy = SubjectSignerBindingPolicy(bindings=bindings)
    (trust / "subject_signer_bindings.json").write_text(json.dumps(policy.model_dump(mode="json")), encoding="utf-8")

    fingerprints = {item.key_id: item.public_key_fingerprint for item in signers}
    for subject, role in signature_guard._REQUIRED_SUBJECTS.items():
        key_id = _key_for_subject(subject)
        envelope = DetachedSignatureEnvelope(
            subject_file=subject,
            subject_sha256="a" * 64,
            signer_role=role,
            key_id=key_id,
            public_key_fingerprint=fingerprints[key_id],
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
            signature_b64=_SIGNATURE,
        )
        name = f"{subject[:-5]}.signature.json"
        (evidence / name).write_text(json.dumps(envelope.model_dump(mode="json")), encoding="utf-8")
    return evidence, trust


def test_exact_subject_to_signer_bindings_verify(tmp_path: Path) -> None:
    evidence, trust = _write_fixture(tmp_path)
    report = assess_subject_signer_bindings(evidence_dir=evidence, trust_dir=trust)
    assert report["status"] == "verified"
    assert report["verified_subject_count"] == report["required_subject_count"]
    assert report["secrets_or_ground_truth_printed"] is False


def test_vendor_owner_key_cannot_sign_another_vendor_subject(tmp_path: Path) -> None:
    evidence, trust = _write_fixture(tmp_path)
    path = evidence / "google_runner_authorization.signature.json"
    envelope = DetachedSignatureEnvelope.model_validate(json.loads(path.read_text(encoding="utf-8")))
    values = envelope.model_dump(mode="python")
    values["key_id"] = _KEYS["crowdstrike"]
    values["public_key_fingerprint"] = "3" * 64
    path.write_text(json.dumps(DetachedSignatureEnvelope(**values).model_dump(mode="json")), encoding="utf-8")
    report = assess_subject_signer_bindings(evidence_dir=evidence, trust_dir=trust)
    assert report["status"] == "blocked"
    assert "subject_signer_binding_mismatch:google_runner_authorization.json" in report["blockers"]


def test_policy_rejects_shared_vendor_owner_key() -> None:
    bindings = []
    for subject, role in signature_guard._REQUIRED_SUBJECTS.items():
        key_id = _key_for_subject(subject)
        if subject in binding_guard._VENDOR_AUTH_SUBJECTS:
            key_id = "shared-vendor-owner-key"
        bindings.append(SubjectSignerBinding(subject_file=subject, signer_role=role, key_id=key_id))
    with pytest.raises(ValueError, match="vendor_keys_must_be_distinct"):
        SubjectSignerBindingPolicy(bindings=tuple(bindings))


def test_workflow_runs_exact_signer_binding_before_crypto_and_scope() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/jarvis-cyber-championship-run.yml").read_text(encoding="utf-8")
    binding = '"$EAY_CHAMPIONSHIP_PYTHON_BIN" -m app.cyber_championship_signer_binding_guard'
    signature = '"$EAY_CHAMPIONSHIP_PYTHON_BIN" -m app.cyber_championship_signature_guard'
    scope = '"$EAY_CHAMPIONSHIP_PYTHON_BIN" -m app.cyber_championship_tenant_scope_guard'
    assert binding in workflow
    assert signature in workflow
    assert scope in workflow
    assert workflow.index(binding) < workflow.index(signature) < workflow.index(scope)
