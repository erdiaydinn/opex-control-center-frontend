"""Exact subject-to-signer binding guard for championship trust roots.

Role-level trust is not sufficient for vendor isolation: a key trusted as a
`vendor_owner` must not be able to sign another vendor's authorization receipt.
This guard binds every externally consumed receipt filename to one exact trusted
role/key identity before cryptographic signature verification runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_championship_signature_guard import (
    DetachedSignatureEnvelope,
    SignerRole,
    TrustedSignerPolicy,
    _REQUIRED_SUBJECTS,
)

SUBJECT_BINDING_CONTRACT = "eay-cyber-championship-subject-signer-bindings-v1"
_VENDOR_AUTH_SUBJECTS = (
    "crowdstrike_runner_authorization.json",
    "google_runner_authorization.json",
    "microsoft_runner_authorization.json",
)


class SubjectSignerBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_file: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}\.json$")
    signer_role: SignerRole
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")


class SubjectSignerBindingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = SUBJECT_BINDING_CONTRACT
    bindings: tuple[SubjectSignerBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def policy_is_complete_and_isolated(self) -> SubjectSignerBindingPolicy:
        by_subject = {item.subject_file: item for item in self.bindings}
        if len(by_subject) != len(self.bindings):
            raise ValueError("subject_signer_binding_duplicate_subject")
        if set(by_subject) != set(_REQUIRED_SUBJECTS):
            raise ValueError("subject_signer_binding_subject_set_incomplete")
        for subject, expected_role in _REQUIRED_SUBJECTS.items():
            if by_subject[subject].signer_role is not expected_role:
                raise ValueError("subject_signer_binding_role_mismatch")
        vendor_keys = tuple(by_subject[subject].key_id for subject in _VENDOR_AUTH_SUBJECTS)
        if len(set(vendor_keys)) != len(vendor_keys):
            raise ValueError("subject_signer_binding_vendor_keys_must_be_distinct")
        return self


def assess_subject_signer_bindings(
    *,
    evidence_dir: Path,
    trust_dir: Path,
) -> dict[str, object]:
    blockers: list[str] = []
    verified_subjects: list[str] = []
    if not evidence_dir.is_dir():
        blockers.append("subject_signer_evidence_directory_missing")
    if not trust_dir.is_dir():
        blockers.append("subject_signer_trust_directory_missing")
    if blockers:
        return _report(blockers, verified_subjects)

    try:
        trusted = TrustedSignerPolicy.model_validate(
            _load_json(trust_dir / "trusted_signers.json")
        )
        policy = SubjectSignerBindingPolicy.model_validate(
            _load_json(trust_dir / "subject_signer_bindings.json")
        )
    except (KeyError, OSError, TypeError, ValueError):
        return _report(["subject_signer_trust_policy_invalid"], verified_subjects)

    trusted_identities = {(item.role, item.key_id) for item in trusted.signers}
    bindings = {item.subject_file: item for item in policy.bindings}
    for subject, expected_role in _REQUIRED_SUBJECTS.items():
        envelope_path = evidence_dir / _signature_file_name(subject)
        if not envelope_path.is_file():
            blockers.append(f"subject_signer_envelope_missing:{subject}")
            continue
        try:
            envelope = DetachedSignatureEnvelope.model_validate(_load_json(envelope_path))
        except (KeyError, OSError, TypeError, ValueError):
            blockers.append(f"subject_signer_envelope_invalid:{subject}")
            continue
        binding = bindings[subject]
        if envelope.subject_file != subject:
            blockers.append(f"subject_signer_subject_mismatch:{subject}")
            continue
        if envelope.signer_role is not expected_role:
            blockers.append(f"subject_signer_role_mismatch:{subject}")
            continue
        if envelope.signer_role is not binding.signer_role or envelope.key_id != binding.key_id:
            blockers.append(f"subject_signer_binding_mismatch:{subject}")
            continue
        if (binding.signer_role, binding.key_id) not in trusted_identities:
            blockers.append(f"subject_signer_key_not_trusted:{subject}")
            continue
        verified_subjects.append(subject)

    if len(verified_subjects) != len(_REQUIRED_SUBJECTS):
        blockers.append("subject_signer_required_bindings_incomplete")
    return _report(blockers, verified_subjects)


def _signature_file_name(subject_name: str) -> str:
    if not subject_name.endswith(".json"):
        raise ValueError("subject_signer_subject_extension_invalid")
    return f"{subject_name[:-5]}.signature.json"


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError("subject_signer_document_must_be_json_object")
    return value


def _report(blockers: list[str], verified_subjects: list[str]) -> dict[str, object]:
    unique_blockers = tuple(dict.fromkeys(blockers))
    return {
        "status": "blocked" if unique_blockers else "verified",
        "blockers": unique_blockers,
        "verified_subject_count": len(verified_subjects),
        "required_subject_count": len(_REQUIRED_SUBJECTS),
        "raw_receipt_contents_printed": False,
        "raw_keys_or_signatures_printed": False,
        "secrets_or_ground_truth_printed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--trust-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = assess_subject_signer_bindings(
        evidence_dir=args.evidence_dir,
        trust_dir=args.trust_dir,
    )
    print(json.dumps(report, sort_keys=True))
    if args.strict and report["status"] != "verified":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
