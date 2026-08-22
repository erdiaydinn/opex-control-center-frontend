from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import app.cyber_championship_execution as execution
import app.cyber_championship_external_authority as external
import app.cyber_championship_vendor_adapters as vendor
from app.cyber_benchmark_intelligence import CyberBenchmarkEvidenceClass
from app.cyber_championship_execution import (
    ChampionshipSandboxAuthorization,
    ChampionshipTrack,
    CompetitorKind,
    SealedTaskBankReceipt,
)
from app.cyber_championship_external_authority import (
    ExternalAdmissionStatus,
    ExternalEvaluatorAuthorityReceipt,
    TrustedEvaluatorPolicy,
    VendorCredentialBindingReceipt,
    VendorPreflightStatus,
    assess_external_championship_admission,
    preflight_vendor_binding,
    verify_external_bank_authority,
)
from app.cyber_championship_vendor_adapters import CompetitorRunnerAuthorization

NOW = datetime(2026, 8, 22, 14, 30, tzinfo=UTC)
ENV = "1" * 64
KEY = "2" * 64


def _bank() -> SealedTaskBankReceipt:
    return execution._seal_model(
        SealedTaskBankReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "bank_id": "bank-rotation-001",
            "rotation_epoch": "rotation-001",
            "task_set_fingerprint": "3" * 64,
            "public_manifest_sha256": "4" * 64,
            "sealed_ground_truth_sha256": "5" * 64,
            "task_count": 110,
            "tracks": tuple(ChampionshipTrack),
            "independent_provider_ref": "org://independent-evaluator",
            "sealed_storage_ref": "sealed://independent-evaluator/bank-001",
            "evaluator_key_id": "key-2026-08",
            "issued_at": NOW,
            "expires_at": NOW + timedelta(days=2),
            "ground_truth_embedded_in_repository": False,
            "ground_truth_visible_to_competitors": False,
            "bank_mutable_after_issue": False,
        },
    )


def _sandbox() -> ChampionshipSandboxAuthorization:
    return execution._seal_model(
        ChampionshipSandboxAuthorization,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "sandbox_id": "sandbox-001",
            "environment_fingerprint": ENV,
            "evidence_class": CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
            "authorization_evidence_ref": "evidence://security-guardian/sandbox-001",
            "worker_attestation_refs": ("attestation://worker/001",),
            "network_policy_ref": "policy://deny-default/championship",
            "workload_identity_ref": "identity://jarvis/championship",
            "authorized_at": NOW,
            "expires_at": NOW + timedelta(hours=4),
            "production_write_allowed": False,
            "exploit_execution_allowed": False,
            "credential_capture_allowed": False,
            "ground_truth_access_allowed": False,
            "unrestricted_network_allowed": False,
        },
    )


def _authority(bank: SealedTaskBankReceipt) -> ExternalEvaluatorAuthorityReceipt:
    return external._seal_model(
        ExternalEvaluatorAuthorityReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "evaluator_org_ref": "org://independent-evaluator",
            "evaluator_identity_ref": "identity://independent-evaluator/service",
            "trusted_issuer_ref": "issuer://independent-evaluator-ca",
            "evaluator_signing_key_id": bank.evaluator_key_id,
            "evaluator_key_fingerprint": KEY,
            "bank_fingerprint": bank.fingerprint,
            "bank_independent_provider_ref": bank.independent_provider_ref,
            "bank_manifest_sha256": bank.public_manifest_sha256,
            "task_set_fingerprint": bank.task_set_fingerprint,
            "sealed_ground_truth_sha256": bank.sealed_ground_truth_sha256,
            "rotation_epoch": bank.rotation_epoch,
            "sealed_storage_ref": bank.sealed_storage_ref,
            "authority_evidence_ref": "evidence://independent-evaluator/authority-001",
            "issued_at": NOW,
            "expires_at": NOW + timedelta(hours=6),
            "independent_of_all_competitors": True,
            "raw_ground_truth_in_receipt": False,
            "private_key_material_present": False,
        },
    )


def _policy() -> TrustedEvaluatorPolicy:
    return TrustedEvaluatorPolicy(
        trusted_issuer_refs=("issuer://independent-evaluator-ca",),
        trusted_key_fingerprints=(KEY,),
        forbidden_competitor_org_refs=(
            "org://crowdstrike",
            "org://google",
            "org://microsoft",
            "org://eay",
        ),
    )


def _vendor_authorization(competitor: CompetitorKind) -> CompetitorRunnerAuthorization:
    identity = f"identity://competition/{competitor.value}"
    resource = f"resource://competition/{competitor.value}"
    values = {
        "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
        "competitor": competitor,
        "organization_ref": f"org://competition/{competitor.value}",
        "identity_binding_refs": (identity,),
        "resource_binding_refs": (resource,),
        "authorization_evidence_ref": f"evidence://owner/{competitor.value}",
        "authorized_at": NOW,
        "expires_at": NOW + timedelta(hours=4),
        "competition_use_authorized": True,
        "read_only_scope_verified": True,
        "credentials_embedded_in_receipt": False,
        "production_mutation_authority": False,
    }
    draft = CompetitorRunnerAuthorization.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return CompetitorRunnerAuthorization(**values, fingerprint=vendor._fingerprint(payload))


def _vendor_binding(competitor: CompetitorKind) -> VendorCredentialBindingReceipt:
    return external._seal_model(
        VendorCredentialBindingReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "competitor": competitor,
            "organization_ref": f"org://competition/{competitor.value}",
            "tenant_ref": f"tenant://competition/{competitor.value}",
            "resource_ref": f"resource://competition/{competitor.value}",
            "workload_identity_ref": f"identity://competition/{competitor.value}",
            "credential_ref": f"vault://championship/{competitor.value}",
            "authorization_evidence_ref": f"evidence://security-guardian/{competitor.value}",
            "environment_fingerprint": ENV,
            "allowed_operation_refs": ("operation://read-only/common-harness",),
            "authorized_at": NOW,
            "expires_at": NOW + timedelta(hours=4),
            "competition_use_authorized": True,
            "read_only_scope_verified": True,
            "identity_verified": True,
            "raw_secret_material_present": False,
            "write_or_admin_scope_present": False,
            "production_mutation_authority": False,
        },
    )


def test_external_evaluator_authority_requires_exact_trusted_bank_binding() -> None:
    bank = _bank()
    verified = verify_external_bank_authority(
        bank=bank,
        authority=_authority(bank),
        policy=_policy(),
        now=NOW + timedelta(minutes=1),
    )
    assert verified.bank_fingerprint == bank.fingerprint
    assert verified.ground_truth_disclosed is False

    wrong = _authority(bank).model_dump(mode="python", exclude={"fingerprint"})
    wrong["task_set_fingerprint"] = "9" * 64
    tampered_binding = external._seal_model(ExternalEvaluatorAuthorityReceipt, wrong)
    with pytest.raises(ValueError, match="bank_binding_mismatch"):
        verify_external_bank_authority(
            bank=bank,
            authority=tampered_binding,
            policy=_policy(),
            now=NOW + timedelta(minutes=1),
        )


def test_external_evaluator_cannot_embed_ground_truth_or_private_key() -> None:
    bank = _bank()
    for field in ("raw_ground_truth_in_receipt", "private_key_material_present"):
        values = _authority(bank).model_dump(mode="python", exclude={"fingerprint"})
        values[field] = True
        with pytest.raises(ValueError, match="boundary_violated"):
            external._seal_model(ExternalEvaluatorAuthorityReceipt, values)


def test_external_evaluator_rejects_untrusted_or_expired_authority() -> None:
    bank = _bank()
    with pytest.raises(ValueError, match="issuer_untrusted"):
        verify_external_bank_authority(
            bank=bank,
            authority=_authority(bank),
            policy=TrustedEvaluatorPolicy(
                trusted_issuer_refs=("issuer://other",),
                trusted_key_fingerprints=(KEY,),
            ),
            now=NOW + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="not_current"):
        verify_external_bank_authority(
            bank=bank,
            authority=_authority(bank),
            policy=_policy(),
            now=NOW + timedelta(days=1),
        )


def test_vendor_binding_accepts_only_secret_manager_reference_and_read_only_scope() -> None:
    competitor = CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI
    values = _vendor_binding(competitor).model_dump(mode="python", exclude={"fingerprint"})
    values["credential_ref"] = "plain-text-token-value"
    with pytest.raises(ValueError, match="secret_manager_reference"):
        external._seal_model(VendorCredentialBindingReceipt, values)

    values = _vendor_binding(competitor).model_dump(mode="python", exclude={"fingerprint"})
    values["write_or_admin_scope_present"] = True
    with pytest.raises(ValueError, match="authority_boundary_violated"):
        external._seal_model(VendorCredentialBindingReceipt, values)


def test_all_three_vendor_preflights_are_required_for_real_run_admission() -> None:
    bank = _bank()
    sandbox = _sandbox()
    verification = verify_external_bank_authority(
        bank=bank,
        authority=_authority(bank),
        policy=_policy(),
        now=NOW + timedelta(minutes=1),
    )
    specs = vendor.default_competitor_adapter_specs()
    preflights = tuple(
        preflight_vendor_binding(
            adapter=spec,
            authorization=_vendor_authorization(spec.competitor),
            binding=_vendor_binding(spec.competitor),
            sandbox=sandbox,
            now=NOW + timedelta(minutes=1),
        )
        for spec in specs
    )
    assert all(item.status is VendorPreflightStatus.READY for item in preflights)

    admitted = assess_external_championship_admission(
        bank=bank,
        sandbox=sandbox,
        evaluator_verification=verification,
        vendor_preflights=preflights,
    )
    assert admitted.status is ExternalAdmissionStatus.READY_FOR_REAL_RUNS
    assert admitted.real_race_executed is False
    assert admitted.verified_leader_claim_allowed is False

    blocked = assess_external_championship_admission(
        bank=bank,
        sandbox=sandbox,
        evaluator_verification=verification,
        vendor_preflights=preflights[:-1],
    )
    assert blocked.status is ExternalAdmissionStatus.EXTERNAL_AUTHORITY_REQUIRED
    assert "external_all_vendor_preflights_not_ready" in blocked.blockers


def test_vendor_preflight_binds_exact_tenant_resource_identity_and_sandbox() -> None:
    sandbox = _sandbox()
    spec = vendor.default_competitor_adapter_specs()[1]
    binding = _vendor_binding(spec.competitor)
    values = binding.model_dump(mode="python", exclude={"fingerprint"})
    values["resource_ref"] = "resource://competition/wrong"
    wrong_binding = external._seal_model(VendorCredentialBindingReceipt, values)
    result = preflight_vendor_binding(
        adapter=spec,
        authorization=_vendor_authorization(spec.competitor),
        binding=wrong_binding,
        sandbox=sandbox,
        now=NOW + timedelta(minutes=1),
    )
    assert result.status is VendorPreflightStatus.BLOCKED
    assert "vendor_binding_resource_mismatch" in result.blockers


def test_real_race_workflow_is_manual_self_hosted_and_least_privilege() -> None:
    root = Path(__file__).resolve().parents[3]
    text = (root / ".github/workflows/jarvis-cyber-championship-run.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in text
    assert "push:" not in text
    assert "pull_request:" not in text
    assert "schedule:" not in text
    assert "contents: read" in text
    assert "environment: cyber-championship" in text
    assert "self-hosted" in text
    assert "eay-championship" in text
    assert "secrets." not in text
    assert "EAY_CHAMPIONSHIP_EVIDENCE_DIR" in text
    assert "run_cyber_championship_external_preflight.py" in text
