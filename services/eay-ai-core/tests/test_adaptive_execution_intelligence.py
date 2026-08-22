from __future__ import annotations

from dataclasses import replace

import pytest

from app.adaptive_execution_intelligence import (
    AdaptiveExecutionRepairPlanner,
    ApiOperationSnapshot,
    DriftKind,
    ExecutionScope,
    OidcMetadataSnapshot,
    RepairDisposition,
    UiTargetSnapshot,
)


@pytest.fixture()
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


@pytest.fixture()
def oidc() -> OidcMetadataSnapshot:
    return OidcMetadataSnapshot(
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


def test_trusted_oidc_endpoint_drift_becomes_sandbox_candidate(scope, oidc):
    planner = AdaptiveExecutionRepairPlanner(scope)
    current = replace(
        oidc,
        authorization_endpoint="https://acme.okta.com/oauth2/default/v2/authorize",
        token_endpoint="https://acme.okta.com/oauth2/default/v2/token",
    )
    proposal = planner.assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.SANDBOX_VERIFY_CANDIDATE
    assert proposal.drift_kind is DriftKind.OIDC_METADATA_CHANGE
    assert proposal.grants_auth_bypass is False
    assert proposal.grants_execution_authority is False
    assert "token_endpoint" in proposal.proposed_adapter


def test_jwks_rotation_is_dynamic_revalidation_candidate(scope, oidc):
    planner = AdaptiveExecutionRepairPlanner(scope)
    current = replace(oidc, jwks_uri="https://acme.okta.com/oauth2/default/v2/keys")
    proposal = planner.assess_oidc_drift(oidc, current)
    assert proposal.drift_kind is DriftKind.OIDC_KEY_ROTATION
    assert proposal.disposition is RepairDisposition.SANDBOX_VERIFY_CANDIDATE
    assert any("signature" in step for step in proposal.verification_requirements)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_are_never_repaired_around(scope, oidc, status):
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(
        oidc, oidc, http_status=status
    )
    assert proposal.disposition is RepairDisposition.HOLD
    assert proposal.drift_kind is DriftKind.AUTHORIZATION_CHANGE


def test_issuer_change_holds(scope, oidc):
    current = replace(oidc, issuer="https://evil.example/oauth2/default")
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.HOLD
    assert proposal.drift_kind is DriftKind.SECURITY_BOUNDARY_CHANGE


def test_http_downgrade_holds(scope, oidc):
    current = replace(oidc, token_endpoint="http://acme.okta.com/oauth2/default/v1/token")
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.HOLD


def test_malformed_endpoint_holds_instead_of_raising(scope, oidc):
    current = replace(oidc, token_endpoint="https://acme.okta.com:bad/token")
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.HOLD


def test_scope_expansion_holds(scope, oidc):
    current = replace(oidc, scopes=oidc.scopes | {"reports.write"})
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.HOLD
    assert proposal.drift_kind is DriftKind.AUTHORIZATION_CHANGE


def test_scope_contraction_requires_review(scope, oidc):
    current = replace(oidc, scopes=frozenset({"openid", "reports.read"}))
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.REVIEW_REQUIRED
    assert proposal.drift_kind is DriftKind.AUTHORIZATION_CHANGE


def test_new_mfa_or_consent_holds_instead_of_bypass(scope, oidc):
    planner = AdaptiveExecutionRepairPlanner(scope)
    mfa = planner.assess_oidc_drift(oidc, replace(oidc, mfa_required=True))
    consent = planner.assess_oidc_drift(oidc, replace(oidc, consent_required=True))
    assert mfa.disposition is RepairDisposition.HOLD
    assert consent.disposition is RepairDisposition.HOLD


def test_unknown_redirect_origin_holds(scope, oidc):
    current = replace(oidc, redirect_uris=frozenset({"https://unknown.example/callback"}))
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_oidc_drift(oidc, current)
    assert proposal.disposition is RepairDisposition.HOLD


def api_snapshot(**overrides) -> ApiOperationSnapshot:
    values = dict(
        tenant_id="tenant-a",
        company_id="company-a",
        semantic_intent="download-daily-report",
        method="GET",
        url="https://api.acme.example/v1/reports/daily",
        operation_id="getDailyReport",
        required_scopes=frozenset({"reports.read"}),
        request_required_fields=frozenset({"date"}),
        response_required_fields=frozenset({"report_id", "download_url"}),
        schema_fingerprint="schema-v1",
    )
    values.update(overrides)
    return ApiOperationSnapshot(**values)


def test_compatible_api_version_move_is_repair_candidate(scope):
    previous = api_snapshot()
    current = api_snapshot(
        url="https://api.acme.example/v2/reports/daily",
        operation_id="getDailyReportV2",
        schema_fingerprint="schema-v2-compatible",
    )
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_api_drift(previous, current)
    assert proposal.disposition is RepairDisposition.SANDBOX_VERIFY_CANDIDATE
    assert proposal.drift_kind is DriftKind.API_ENDPOINT_CHANGE
    assert proposal.requires_outcome_verification is True


def test_new_required_api_input_holds(scope):
    previous = api_snapshot()
    current = api_snapshot(request_required_fields=frozenset({"date", "region"}))
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_api_drift(previous, current)
    assert proposal.disposition is RepairDisposition.HOLD
    assert proposal.drift_kind is DriftKind.API_SCHEMA_BREAKING_CHANGE


def test_missing_required_api_output_holds(scope):
    previous = api_snapshot()
    current = api_snapshot(response_required_fields=frozenset({"report_id"}))
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_api_drift(previous, current)
    assert proposal.disposition is RepairDisposition.HOLD


def test_api_privilege_expansion_holds(scope):
    previous = api_snapshot()
    current = api_snapshot(required_scopes=frozenset({"reports.read", "reports.write"}))
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_api_drift(previous, current)
    assert proposal.disposition is RepairDisposition.HOLD
    assert proposal.drift_kind is DriftKind.AUTHORIZATION_CHANGE


def test_api_403_is_not_routed_around(scope):
    previous = api_snapshot()
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_api_drift(
        previous, previous, http_status=403
    )
    assert proposal.disposition is RepairDisposition.HOLD


def test_semantic_ui_relocation_can_be_repaired_with_outcome_verification(scope):
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
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_ui_drift(previous, current)
    assert proposal.drift_kind is DriftKind.UI_SEMANTIC_RELOCATION
    assert proposal.disposition is RepairDisposition.SANDBOX_VERIFY_CANDIDATE
    assert any("coordinate-only" in step for step in proposal.verification_requirements)
    assert proposal.requires_outcome_verification is True


def test_ui_context_change_requires_review(scope):
    previous = UiTargetSnapshot(
        tenant_id="tenant-a",
        company_id="company-a",
        semantic_intent="export-excel",
        role="button",
        label="Export",
        context_fingerprint="report-page-v1",
    )
    current = replace(previous, context_fingerprint="admin-delete-page")
    proposal = AdaptiveExecutionRepairPlanner(scope).assess_ui_drift(previous, current)
    assert proposal.disposition is RepairDisposition.REVIEW_REQUIRED


def test_cross_tenant_repair_is_forbidden(scope):
    previous = api_snapshot()
    current = api_snapshot(tenant_id="tenant-b")
    with pytest.raises(ValueError, match="cross-tenant/company"):
        AdaptiveExecutionRepairPlanner(scope).assess_api_drift(previous, current)


def test_proposal_fingerprint_is_deterministic(scope):
    previous = api_snapshot()
    current = api_snapshot(url="https://api.acme.example/v2/reports/daily")
    planner = AdaptiveExecutionRepairPlanner(scope)
    first = planner.assess_api_drift(previous, current)
    second = planner.assess_api_drift(previous, current)
    assert first.proposal_fingerprint == second.proposal_fingerprint
    assert len(first.proposal_fingerprint) == 64
