from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.cyber_championship_execution import (
    ChampionshipSandboxAuthorization,
    SealedTaskBankReceipt,
)
from app.cyber_championship_external_authority import (
    ExternalEvaluatorAuthorityReceipt,
    TrustedEvaluatorPolicy,
    VendorCredentialBindingReceipt,
    assess_external_championship_admission,
    preflight_vendor_binding,
    verify_external_bank_authority,
)
from app.cyber_championship_vendor_adapters import (
    CompetitorRunnerAuthorization,
    default_competitor_adapter_specs,
)

_REQUIRED_FILES = (
    "sealed_bank.json",
    "sandbox_authorization.json",
    "evaluator_authority.json",
    "evaluator_trust_policy.json",
    "crowdstrike_runner_authorization.json",
    "crowdstrike_credential_binding.json",
    "google_runner_authorization.json",
    "google_credential_binding.json",
    "microsoft_runner_authorization.json",
    "microsoft_credential_binding.json",
)
_STEMS = {
    "crowdstrike_charlotte_ai": "crowdstrike",
    "google_security_operations_gemini": "google",
    "microsoft_security_copilot": "microsoft",
}


def _load(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError("championship_receipt_must_be_json_object")
    return value


def _blocked(blockers: list[str]) -> dict[str, object]:
    return {
        "status": "external_authority_required",
        "blockers": blockers,
        "real_race_executed": False,
        "verified_leader_claim_allowed": False,
        "production_security_superiority_claim_allowed": False,
        "secrets_or_ground_truth_printed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if args.evidence_dir is None:
        print(json.dumps(_blocked(["external_evidence_directory_not_mounted"]), sort_keys=True))
        return 2 if args.strict else 0

    missing = [name for name in _REQUIRED_FILES if not (args.evidence_dir / name).is_file()]
    if missing:
        print(
            json.dumps(
                _blocked([f"external_receipt_missing:{name}" for name in missing]),
                sort_keys=True,
            )
        )
        return 2 if args.strict else 0

    try:
        bank = SealedTaskBankReceipt.model_validate(_load(args.evidence_dir / "sealed_bank.json"))
        sandbox = ChampionshipSandboxAuthorization.model_validate(
            _load(args.evidence_dir / "sandbox_authorization.json")
        )
        authority = ExternalEvaluatorAuthorityReceipt.model_validate(
            _load(args.evidence_dir / "evaluator_authority.json")
        )
        policy = TrustedEvaluatorPolicy.model_validate(
            _load(args.evidence_dir / "evaluator_trust_policy.json")
        )
        now = datetime.now(UTC)
        evaluator = verify_external_bank_authority(
            bank=bank,
            authority=authority,
            policy=policy,
            now=now,
        )
        preflights = []
        for spec in default_competitor_adapter_specs():
            stem = _STEMS[spec.competitor.value]
            authorization = CompetitorRunnerAuthorization.model_validate(
                _load(args.evidence_dir / f"{stem}_runner_authorization.json")
            )
            binding = VendorCredentialBindingReceipt.model_validate(
                _load(args.evidence_dir / f"{stem}_credential_binding.json")
            )
            preflights.append(
                preflight_vendor_binding(
                    adapter=spec,
                    authorization=authorization,
                    binding=binding,
                    sandbox=sandbox,
                    now=now,
                )
            )
        admission = assess_external_championship_admission(
            bank=bank,
            sandbox=sandbox,
            evaluator_verification=evaluator,
            vendor_preflights=tuple(preflights),
        )
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps(_blocked([f"external_receipt_validation_failed:{exc}"]), sort_keys=True))
        return 2 if args.strict else 0

    report = {
        "status": admission.status.value,
        "admission_fingerprint": admission.fingerprint,
        "bank_fingerprint": admission.bank_fingerprint,
        "sandbox_fingerprint": admission.sandbox_fingerprint,
        "evaluator_verification_fingerprint": admission.evaluator_verification_fingerprint,
        "vendor_preflight_fingerprints": admission.vendor_preflight_fingerprints,
        "blockers": admission.blockers,
        "real_race_executed": False,
        "verified_leader_claim_allowed": False,
        "production_security_superiority_claim_allowed": False,
        "secrets_or_ground_truth_printed": False,
    }
    print(json.dumps(report, sort_keys=True))
    if args.strict and admission.status.value != "ready_for_real_runs":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
