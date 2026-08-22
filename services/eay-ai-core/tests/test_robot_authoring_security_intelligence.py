from __future__ import annotations

import pytest

from app.adaptive_execution_intelligence import (
    AdaptiveExecutionRepairPlanner,
    AdaptiveRepairProposal,
    ApiOperationSnapshot,
    DriftKind,
    ExecutionScope,
    RepairDisposition,
)
from app.robot_authoring_intelligence import (
    RobotAuthoringCandidate,
    RobotDefinition,
    RobotKind,
    RobotRegistryCandidate,
    SandboxEffectStatus,
    author_repair_candidate,
    build_registry_candidate,
    issue_sandbox_receipt,
)

OUTCOME = "a" * 64
ENVIRONMENT = "b" * 64


def _scope() -> ExecutionScope:
    return ExecutionScope(
        tenant_id="tenant-a",
        company_id="company-a",
        objective_id="daily-report",
        trusted_origins=frozenset({"https://api.acme.example"}),
        trusted_issuers=frozenset({"https://acme.okta.com/oauth2/default"}),
        allowed_scopes=frozenset({"reports.read"}),
        allowed_audiences=frozenset({"api://reports"}),
        allowed_redirect_origins=frozenset({"https://jarvis.acme.example"}),
    )


def _robot() -> RobotDefinition:
    return RobotDefinition(
        tenant_id="tenant-a",
        company_id="company-a",
        objective_id="daily-report",
        robot_id="daily-report-download",
        version=7,
        kind=RobotKind.API,
        semantic_intent="download-daily-report",
        capability_ref="reports.download",
        manifest=(
            ("method", "GET"),
            ("url", "https://api.acme.example/v1/reports/daily"),
            ("operation_id", "getDailyReport"),
        ),
        expected_outcome_fingerprint=OUTCOME,
    )


def _snapshot(**overrides) -> ApiOperationSnapshot:
    values = {
        "tenant_id": "tenant-a",
        "company_id": "company-a",
        "semantic_intent": "download-daily-report",
        "method": "GET",
        "url": "https://api.acme.example/v1/reports/daily",
        "operation_id": "getDailyReport",
        "required_scopes": frozenset({"reports.read"}),
        "request_required_fields": frozenset({"date"}),
        "response_required_fields": frozenset({"report_id", "download_url"}),
        "schema_fingerprint": "schema-v1",
    }
    values.update(overrides)
    return ApiOperationSnapshot(**values)


def _candidate() -> RobotAuthoringCandidate:
    repair_scope = _scope()
    previous = _snapshot()
    current = _snapshot(
        url="https://api.acme.example/v2/reports/daily",
        operation_id="getDailyReportV2",
        schema_fingerprint="schema-v2-compatible",
    )
    proposal = AdaptiveExecutionRepairPlanner(repair_scope).assess_api_drift(
        previous,
        current,
    )
    result = author_repair_candidate(
        robot=_robot(),
        repair_scope=repair_scope,
        proposal=proposal,
    )
    assert result.candidate is not None
    return result.candidate


def _receipt(candidate: RobotAuthoringCandidate, verifier_id: str):
    return issue_sandbox_receipt(
        candidate=candidate,
        environment_fingerprint=ENVIRONMENT,
        verifier_id=verifier_id,
        effect_status=SandboxEffectStatus.VERIFIED_EQUIVALENT,
        observed_outcome_fingerprint=OUTCOME,
        evidence_refs=(f"sandbox://{verifier_id}/effect",),
    )


def test_forged_allowed_url_field_still_cannot_leave_trusted_origin():
    proposal = AdaptiveRepairProposal(
        drift_kind=DriftKind.API_ENDPOINT_CHANGE,
        disposition=RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
        reasons=("adversarial forged proposal",),
        verification_requirements=("sandbox",),
        proposed_adapter={"url": "https://evil.example/v2/reports/daily"},
        proposal_fingerprint="c" * 64,
    )
    result = author_repair_candidate(
        robot=_robot(),
        repair_scope=_scope(),
        proposal=proposal,
    )
    assert result.blockers == ("adaptive_repair_url_not_trusted",)


def test_forged_http_method_change_is_independently_rejected():
    proposal = AdaptiveRepairProposal(
        drift_kind=DriftKind.API_ENDPOINT_CHANGE,
        disposition=RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
        reasons=("adversarial forged proposal",),
        verification_requirements=("sandbox",),
        proposed_adapter={"method": "POST"},
        proposal_fingerprint="d" * 64,
    )
    result = author_repair_candidate(
        robot=_robot(),
        repair_scope=_scope(),
        proposal=proposal,
    )
    assert result.blockers == ("adaptive_repair_http_method_change_forbidden",)


def test_robot_candidate_fingerprint_is_revalidated_on_model_load():
    candidate = _candidate()
    payload = candidate.model_dump()
    payload["robot_id"] = "tampered-robot"
    with pytest.raises(ValueError, match="candidate_fingerprint_mismatch"):
        RobotAuthoringCandidate(**payload)


def test_registry_candidate_fingerprint_is_revalidated_on_model_load():
    candidate = _candidate()
    registry = build_registry_candidate(
        candidate=candidate,
        receipts=(
            _receipt(candidate, "verifier-a"),
            _receipt(candidate, "verifier-b"),
        ),
    )
    payload = registry.model_dump()
    payload["robot_id"] = "tampered-robot"
    with pytest.raises(ValueError, match="registry_candidate_fingerprint_mismatch"):
        RobotRegistryCandidate(**payload)


def test_https_downgrade_is_rejected_again_at_authoring_boundary():
    proposal = AdaptiveRepairProposal(
        drift_kind=DriftKind.API_ENDPOINT_CHANGE,
        disposition=RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
        reasons=("adversarial forged proposal",),
        verification_requirements=("sandbox",),
        proposed_adapter={"url": "http://api.acme.example/v2/reports/daily"},
        proposal_fingerprint="e" * 64,
    )
    result = author_repair_candidate(
        robot=_robot(),
        repair_scope=_scope(),
        proposal=proposal,
    )
    assert result.blockers == ("adaptive_repair_url_requires_https",)
