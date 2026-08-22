from __future__ import annotations

from dataclasses import replace

import pytest

from app.adaptive_execution_intelligence import (
    AdaptiveExecutionRepairPlanner,
    AdaptiveRepairProposal,
    ApiOperationSnapshot,
    DriftKind,
    ExecutionScope,
    OidcMetadataSnapshot,
    RepairDisposition,
    UiTargetSnapshot,
)
from app.robot_authoring_intelligence import (
    RobotAuthoringDisposition,
    RobotDefinition,
    RobotKind,
    SandboxEffectStatus,
    SandboxVerificationReceipt,
    author_repair_candidate,
    build_registry_candidate,
    issue_sandbox_receipt,
)

OUTCOME = "a" * 64
ENVIRONMENT = "b" * 64


def scope() -> ExecutionScope:
    return ExecutionScope(
        tenant_id="tenant-a",
        company_id="company-a",
        objective_id="daily-report",
        trusted_origins=frozenset({"https://acme.okta.com", "https://api.acme.example"}),
        trusted_issuers=frozenset({"https://acme.okta.com/oauth2/default"}),
        allowed_scopes=frozenset({"openid", "profile", "reports.read"}),
        allowed_audiences=frozenset({"api://reports"}),
        allowed_redirect_origins=frozenset({"https://jarvis.acme.example"}),
    )


def api_robot() -> RobotDefinition:
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


def api_snapshot(**overrides) -> ApiOperationSnapshot:
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


def api_repair(repair_scope: ExecutionScope) -> AdaptiveRepairProposal:
    previous = api_snapshot()
    current = api_snapshot(
        url="https://api.acme.example/v2/reports/daily",
        operation_id="getDailyReportV2",
        schema_fingerprint="schema-v2-compatible",
    )
    return AdaptiveExecutionRepairPlanner(repair_scope).assess_api_drift(previous, current)


def candidate(repair_scope: ExecutionScope, robot: RobotDefinition):
    result = author_repair_candidate(
        robot=robot,
        repair_scope=repair_scope,
        proposal=api_repair(repair_scope),
    )
    assert result.candidate is not None
    return result.candidate


def sandbox_receipt(candidate_value, verifier_id: str, **overrides):
    values = {
        "candidate": candidate_value,
        "environment_fingerprint": ENVIRONMENT,
        "verifier_id": verifier_id,
        "effect_status": SandboxEffectStatus.VERIFIED_EQUIVALENT,
        "observed_outcome_fingerprint": OUTCOME,
        "evidence_refs": (f"sandbox://{verifier_id}/effect",),
    }
    values.update(overrides)
    return issue_sandbox_receipt(**values)


def test_api_drift_authors_structured_candidate_without_authority():
    repair_scope = scope()
    robot = api_robot()
    result = author_repair_candidate(
        robot=robot,
        repair_scope=repair_scope,
        proposal=api_repair(repair_scope),
    )

    assert result.disposition is RobotAuthoringDisposition.STRUCTURED_CANDIDATE
    assert result.candidate is not None
    authored = result.candidate
    assert authored.source_version == 7
    assert authored.proposed_version == 8
    assert authored.grants_auth_bypass is False
    assert authored.grants_execution_authority is False
    assert authored.can_auto_publish is False
    assert {item.field for item in authored.patches} == {"url", "operation_id"}
    assert dict(authored.candidate_manifest)["url"].endswith("/v2/reports/daily")
    assert dict(authored.candidate_manifest)["operation_id"] == "getDailyReportV2"


def test_oidc_key_rotation_authors_only_jwks_patch():
    repair_scope = scope()
    oidc = OidcMetadataSnapshot(
        tenant_id="tenant-a",
        company_id="company-a",
        issuer="https://acme.okta.com/oauth2/default",
        authorization_endpoint="https://acme.okta.com/oauth2/default/v1/authorize",
        token_endpoint="https://acme.okta.com/oauth2/default/v1/token",
        jwks_uri="https://acme.okta.com/oauth2/default/v1/keys",
        scopes=frozenset({"openid", "profile", "reports.read"}),
        audiences=frozenset({"api://reports"}),
        redirect_uris=frozenset({"https://jarvis.acme.example/callback"}),
        policy_fingerprint="policy-v1",
    )
    current = replace(oidc, jwks_uri="https://acme.okta.com/oauth2/default/v2/keys")
    proposal = AdaptiveExecutionRepairPlanner(repair_scope).assess_oidc_drift(oidc, current)
    robot = RobotDefinition(
        tenant_id="tenant-a",
        company_id="company-a",
        objective_id="daily-report",
        robot_id="okta-auth-session",
        version=3,
        kind=RobotKind.HYBRID,
        semantic_intent="establish-authorized-session",
        capability_ref="auth.session",
        manifest=(
            ("authorization_endpoint", oidc.authorization_endpoint),
            ("token_endpoint", oidc.token_endpoint),
            ("jwks_uri", oidc.jwks_uri),
        ),
        expected_outcome_fingerprint=OUTCOME,
    )

    result = author_repair_candidate(
        robot=robot,
        repair_scope=repair_scope,
        proposal=proposal,
    )

    assert result.candidate is not None
    assert tuple(item.field for item in result.candidate.patches) == ("jwks_uri",)
    assert result.candidate.grants_auth_bypass is False


def test_ui_semantic_relocation_authors_semantic_patch_only():
    repair_scope = scope()
    previous = UiTargetSnapshot(
        tenant_id="tenant-a",
        company_id="company-a",
        semantic_intent="export-excel",
        role="button",
        label="Export",
        context_fingerprint="report-page-v1",
        spatial_hint="top-right",
    )
    current = replace(
        previous,
        role="menuitem",
        label="Download Excel",
        spatial_hint="overflow-menu",
    )
    proposal = AdaptiveExecutionRepairPlanner(repair_scope).assess_ui_drift(previous, current)
    robot = RobotDefinition(
        tenant_id="tenant-a",
        company_id="company-a",
        objective_id="daily-report",
        robot_id="export-report-ui",
        version=4,
        kind=RobotKind.PLAYWRIGHT,
        semantic_intent="export-excel",
        capability_ref="reports.export",
        manifest=(
            ("role", "button"),
            ("label", "Export"),
            ("spatial_hint", "top-right"),
        ),
        expected_outcome_fingerprint=OUTCOME,
    )

    result = author_repair_candidate(
        robot=robot,
        repair_scope=repair_scope,
        proposal=proposal,
    )

    assert result.candidate is not None
    assert {item.field for item in result.candidate.patches} == {
        "role",
        "label",
        "spatial_hint",
    }


def test_auth_denial_never_becomes_robot_revision():
    repair_scope = scope()
    previous = api_snapshot()
    proposal = AdaptiveExecutionRepairPlanner(repair_scope).assess_api_drift(
        previous,
        previous,
        http_status=403,
    )

    result = author_repair_candidate(
        robot=api_robot(),
        repair_scope=repair_scope,
        proposal=proposal,
    )

    assert result.disposition is RobotAuthoringDisposition.HOLD
    assert result.candidate is None


def test_unapproved_arbitrary_script_patch_is_rejected():
    repair_scope = scope()
    proposal = AdaptiveRepairProposal(
        drift_kind=DriftKind.API_ENDPOINT_CHANGE,
        disposition=RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
        reasons=("synthetic adversarial proposal",),
        verification_requirements=("sandbox",),
        proposed_adapter={"script": "fetch('/admin')"},
        proposal_fingerprint="c" * 64,
    )

    result = author_repair_candidate(
        robot=api_robot(),
        repair_scope=repair_scope,
        proposal=proposal,
    )

    assert result.disposition is RobotAuthoringDisposition.HOLD
    assert result.blockers == ("adaptive_repair_contains_unapproved_patch_field",)


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("tenant_id", "tenant-b", "robot_authoring_tenant_mismatch"),
        ("company_id", "company-b", "robot_authoring_company_mismatch"),
        ("objective_id", "other-objective", "robot_authoring_objective_mismatch"),
    ],
)
def test_cross_scope_authoring_is_rejected(field, value, blocker):
    repair_scope = scope()
    robot = api_robot().model_copy(update={field: value})
    result = author_repair_candidate(
        robot=robot,
        repair_scope=repair_scope,
        proposal=api_repair(repair_scope),
    )
    assert result.disposition is RobotAuthoringDisposition.HOLD
    assert result.blockers == (blocker,)


def test_noop_patch_cannot_create_new_robot_revision():
    repair_scope = scope()
    proposal = AdaptiveRepairProposal(
        drift_kind=DriftKind.API_ENDPOINT_CHANGE,
        disposition=RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
        reasons=("synthetic no-op",),
        verification_requirements=("sandbox",),
        proposed_adapter={"url": "https://api.acme.example/v1/reports/daily"},
        proposal_fingerprint="d" * 64,
    )

    result = author_repair_candidate(
        robot=api_robot(),
        repair_scope=repair_scope,
        proposal=proposal,
    )

    assert result.disposition is RobotAuthoringDisposition.HOLD
    assert result.blockers == ("adaptive_repair_produced_no_robot_change",)


def test_sandbox_receipt_is_deterministic_and_tamper_evident():
    authored = candidate(scope(), api_robot())
    first = sandbox_receipt(authored, "verifier-a")
    second = sandbox_receipt(authored, "verifier-a")
    assert first.receipt_fingerprint == second.receipt_fingerprint

    payload = first.model_dump()
    payload["production_write_count"] = 1
    with pytest.raises(ValueError, match="fingerprint_mismatch"):
        SandboxVerificationReceipt(**payload)


def test_two_independent_equivalent_sandbox_receipts_create_registry_candidate():
    authored = candidate(scope(), api_robot())
    first = sandbox_receipt(authored, "verifier-a")
    second = sandbox_receipt(authored, "verifier-b")

    registry = build_registry_candidate(
        candidate=authored,
        receipts=(first, second),
    )

    assert registry.approval_required is True
    assert registry.executable is False
    assert registry.production_activated is False
    assert registry.can_auto_publish is False
    assert registry.independent_verifier_ids == ("verifier-a", "verifier-b")
    assert len(registry.sandbox_receipt_fingerprints) == 2


def test_single_sandbox_receipt_cannot_reach_registry_review():
    authored = candidate(scope(), api_robot())
    first = sandbox_receipt(authored, "verifier-a")
    with pytest.raises(ValueError, match="two_sandbox_receipts"):
        build_registry_candidate(candidate=authored, receipts=(first,))


def test_same_sandbox_verifier_twice_is_not_independent_quorum():
    authored = candidate(scope(), api_robot())
    first = sandbox_receipt(authored, "verifier-a", evidence_refs=("sandbox://a/one",))
    second = sandbox_receipt(authored, "verifier-a", evidence_refs=("sandbox://a/two",))
    with pytest.raises(ValueError, match="two_independent_sandbox_verifiers"):
        build_registry_candidate(candidate=authored, receipts=(first, second))


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"network_policy": "open"}, "network_policy_not_fail_closed"),
        ({"production_write_count": 1}, "contains_production_write"),
        ({"auth_bypass_observed": True}, "observed_auth_bypass"),
        ({"execution_authority_minted": True}, "minted_execution_authority"),
        (
            {
                "effect_status": SandboxEffectStatus.UNKNOWN,
                "observed_outcome_fingerprint": None,
            },
            "outcome_not_verified_equivalent",
        ),
        (
            {
                "effect_status": SandboxEffectStatus.VERIFIED_NOT_EQUIVALENT,
                "observed_outcome_fingerprint": "e" * 64,
            },
            "outcome_not_verified_equivalent",
        ),
        ({"observed_outcome_fingerprint": "e" * 64}, "business_outcome_mismatch"),
    ],
)
def test_unsafe_sandbox_evidence_cannot_promote(overrides, match):
    authored = candidate(scope(), api_robot())
    unsafe = sandbox_receipt(authored, "verifier-a", **overrides)
    safe = sandbox_receipt(authored, "verifier-b")
    with pytest.raises(ValueError, match=match):
        build_registry_candidate(candidate=authored, receipts=(unsafe, safe))


def test_receipt_for_different_candidate_cannot_promote():
    repair_scope = scope()
    authored = candidate(repair_scope, api_robot())
    other_robot = api_robot().model_copy(update={"robot_id": "other-robot"})
    other_candidate = candidate(repair_scope, other_robot)
    wrong = sandbox_receipt(other_candidate, "verifier-a")
    safe = sandbox_receipt(authored, "verifier-b")
    with pytest.raises(ValueError, match="candidate_mismatch"):
        build_registry_candidate(candidate=authored, receipts=(wrong, safe))
