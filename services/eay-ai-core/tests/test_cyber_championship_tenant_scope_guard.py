from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import app.cyber_championship_execution as execution
import app.cyber_championship_external_authority as external
import app.cyber_championship_tenant_scope_guard as scope_guard
import app.cyber_championship_vendor_adapters as vendor
from app.cyber_championship_execution import CompetitorKind
from app.cyber_championship_external_authority import VendorCredentialBindingReceipt
from app.cyber_championship_tenant_scope_guard import (
    VendorScopeGuardStatus,
    evaluate_vendor_scope_guard,
)
from app.cyber_championship_vendor_adapters import CompetitorRunnerAuthorization

NOW = datetime(2026, 8, 22, 15, 30, tzinfo=UTC)
ENV = "a" * 64


def _authorization(competitor: CompetitorKind) -> CompetitorRunnerAuthorization:
    identity = f"identity://competition/{competitor.value}"
    tenant = f"tenant://competition/{competitor.value}"
    resource = f"resource://competition/{competitor.value}"
    values = {
        "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
        "competitor": competitor,
        "organization_ref": f"org://competition/{competitor.value}",
        "identity_binding_refs": (identity,),
        "resource_binding_refs": (tenant, resource),
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


def _binding(competitor: CompetitorKind) -> VendorCredentialBindingReceipt:
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


def test_scope_guard_accepts_exact_tenant_resource_identity_and_operation() -> None:
    for competitor in (
        CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI,
        CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI,
        CompetitorKind.MICROSOFT_SECURITY_COPILOT,
    ):
        receipt = evaluate_vendor_scope_guard(
            authorization=_authorization(competitor),
            binding=_binding(competitor),
        )
        assert receipt.status is VendorScopeGuardStatus.READY
        assert receipt.blockers == ()
        assert receipt.raw_credentials_observed is False
        assert receipt.production_mutation_authority is False


def test_scope_guard_blocks_wrong_tenant_even_when_resource_and_identity_match() -> None:
    competitor = CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI
    values = _binding(competitor).model_dump(mode="python", exclude={"fingerprint"})
    values["tenant_ref"] = "tenant://competition/wrong"
    wrong_binding = external._seal_model(VendorCredentialBindingReceipt, values)
    receipt = evaluate_vendor_scope_guard(
        authorization=_authorization(competitor),
        binding=wrong_binding,
    )
    assert receipt.status is VendorScopeGuardStatus.BLOCKED
    assert "vendor_scope_tenant_not_authorized" in receipt.blockers


def test_scope_guard_blocks_extra_resource_authority() -> None:
    competitor = CompetitorKind.MICROSOFT_SECURITY_COPILOT
    authorization = _authorization(competitor)
    values = authorization.model_dump(mode="python", exclude={"fingerprint"})
    values["resource_binding_refs"] = (
        *authorization.resource_binding_refs,
        "resource://competition/unrelated-admin-scope",
    )
    draft = CompetitorRunnerAuthorization.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    widened = CompetitorRunnerAuthorization(**values, fingerprint=vendor._fingerprint(payload))
    receipt = evaluate_vendor_scope_guard(
        authorization=widened,
        binding=_binding(competitor),
    )
    assert receipt.status is VendorScopeGuardStatus.BLOCKED
    assert "vendor_scope_resource_set_not_least_privilege" in receipt.blockers


def test_scope_guard_blocks_noncanonical_operation() -> None:
    competitor = CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI
    values = _binding(competitor).model_dump(mode="python", exclude={"fingerprint"})
    values["allowed_operation_refs"] = ("operation://read-only/other-workload",)
    widened = external._seal_model(VendorCredentialBindingReceipt, values)
    receipt = evaluate_vendor_scope_guard(
        authorization=_authorization(competitor),
        binding=widened,
    )
    assert receipt.status is VendorScopeGuardStatus.BLOCKED
    assert "vendor_scope_operation_not_exact_read_only_harness" in receipt.blockers


def test_authorized_workflow_runs_scope_guard_before_external_preflight() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github/workflows/jarvis-cyber-championship-run.yml"
    ).read_text(encoding="utf-8")
    guard = "python -m app.cyber_championship_tenant_scope_guard"
    preflight = "python scripts/run_cyber_championship_external_preflight.py"
    assert guard in workflow
    assert preflight in workflow
    assert workflow.index(guard) < workflow.index(preflight)
    assert "--strict" in workflow
    assert "secrets." not in workflow


def test_scope_guard_cli_never_reports_raw_validation_values(tmp_path: Path) -> None:
    (tmp_path / "crowdstrike_runner_authorization.json").write_text(
        '{"credential":"do-not-print-this"}',
        encoding="utf-8",
    )
    report = scope_guard.assess_evidence_directory(tmp_path)
    rendered = str(report)
    assert report["status"] == "blocked"
    assert "do-not-print-this" not in rendered
    assert report["secrets_or_ground_truth_printed"] is False
