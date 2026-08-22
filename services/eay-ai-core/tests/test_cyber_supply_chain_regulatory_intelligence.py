from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.cyber_supply_chain_regulatory_intelligence import (
    CraEvidenceState,
    CraOccurrenceType,
    CraProductScope,
    CraReportabilityInput,
    CraReportabilityStatus,
    ExternalSupplyChainObservation,
    GovernedDependencyComponent,
    PackageCoordinate,
    SupplyChainMatchStatus,
    SupplyChainThreatType,
    assess_cra_reportability,
    match_supply_chain_observation,
)


def package(version: str = "1.0.0") -> PackageCoordinate:
    return PackageCoordinate(ecosystem="npm", package_name="permit2", exact_version=version)


def observation(version: str = "1.0.0") -> ExternalSupplyChainObservation:
    return ExternalSupplyChainObservation(
        source_id="osv_dev",
        record_id="MAL-2026-TEST",
        threat_type=SupplyChainThreatType.MALICIOUS_PACKAGE,
        package=package(version),
        observed_at=datetime(2026, 8, 23, tzinfo=UTC),
        source_fingerprint="a" * 64,
    )


def component(
    version: str = "1.0.0",
    *,
    inventory_verified: bool = True,
    production_deployment_verified: bool = False,
) -> GovernedDependencyComponent:
    return GovernedDependencyComponent(
        tenant_id="eay",
        inventory_fingerprint="b" * 64,
        package=package(version),
        inventory_verified=inventory_verified,
        production_deployment_verified=production_deployment_verified,
    )


def test_malicious_package_is_first_class_and_not_a_cve_alias():
    value = observation()
    assert value.record_id.startswith("MAL-")
    assert value.threat_type is SupplyChainThreatType.MALICIOUS_PACKAGE
    assert value.threat_type is not SupplyChainThreatType.VULNERABILITY


def test_supply_chain_match_requires_ecosystem_name_and_exact_version():
    matched = match_supply_chain_observation(observation("1.0.0"), component("1.0.0"))
    assert matched.status is SupplyChainMatchStatus.INVENTORY_MATCH_REVIEW_REQUIRED
    assert matched.exact_package_match is True
    assert matched.eay_affected_claim_allowed is False
    assert matched.incident_claim_allowed is False
    assert matched.execution_authority_granted is False

    wrong_version = match_supply_chain_observation(observation("1.0.0"), component("1.0.1"))
    assert wrong_version.status is SupplyChainMatchStatus.NO_EXACT_MATCH
    assert wrong_version.exact_package_match is False
    assert wrong_version.eay_affected_claim_allowed is False


def test_verified_production_match_still_requires_exposure_review():
    decision = match_supply_chain_observation(
        observation(),
        component(production_deployment_verified=True),
    )
    assert decision.status is SupplyChainMatchStatus.PRODUCTION_EXPOSURE_REVIEW_REQUIRED
    assert decision.eay_affected_claim_allowed is False
    assert decision.incident_claim_allowed is False


def test_external_observation_cannot_mint_eay_or_execution_authority():
    payload = observation().model_dump(mode="json")
    for field in (
        "company_exposure_authority",
        "incident_confirmation_authority",
        "execution_authority_granted",
    ):
        tampered = dict(payload)
        tampered[field] = True
        with pytest.raises(ValidationError):
            ExternalSupplyChainObservation.model_validate(tampered)


def cra_input(
    *,
    awareness_at: datetime | None = None,
    company_impact: CraEvidenceState = CraEvidenceState.VERIFIED,
    active_exploitation: CraEvidenceState = CraEvidenceState.VERIFIED,
    product_scope: CraProductScope = CraProductScope.IN_SCOPE,
    corrective_measure_available_at: datetime | None = None,
) -> CraReportabilityInput:
    return CraReportabilityInput(
        occurrence_type=CraOccurrenceType.ACTIVELY_EXPLOITED_VULNERABILITY,
        awareness_at=awareness_at or datetime(2026, 9, 11, 10, tzinfo=UTC),
        company_impact=company_impact,
        active_exploitation=active_exploitation,
        product_scope=product_scope,
        corrective_measure_available_at=corrective_measure_available_at,
    )


def test_cra_reporting_clock_starts_only_after_all_governed_gates_pass():
    awareness = datetime(2026, 9, 11, 10, tzinfo=UTC)
    corrective = datetime(2026, 9, 12, 8, tzinfo=UTC)
    decision = assess_cra_reportability(
        cra_input(awareness_at=awareness, corrective_measure_available_at=corrective)
    )
    assert decision.status is CraReportabilityStatus.HUMAN_REPORTING_REVIEW_REQUIRED
    assert decision.reportable_candidate is True
    assert decision.reporting_clock is not None
    assert decision.reporting_clock.early_warning_due_at == datetime(
        2026, 9, 12, 10, tzinfo=UTC
    )
    assert decision.reporting_clock.notification_due_at == datetime(
        2026, 9, 14, 10, tzinfo=UTC
    )
    assert decision.reporting_clock.final_report_due_at == datetime(
        2026, 9, 26, 8, tzinfo=UTC
    )
    assert decision.human_approval_required is True
    assert decision.automatic_submission_permitted is False
    assert decision.execution_authority_granted is False


def test_cra_fails_closed_when_company_impact_exploitation_or_scope_is_unverified():
    cases = (
        (
            cra_input(company_impact=CraEvidenceState.UNVERIFIED),
            CraReportabilityStatus.HOLD_COMPANY_IMPACT_UNVERIFIED,
        ),
        (
            cra_input(active_exploitation=CraEvidenceState.UNVERIFIED),
            CraReportabilityStatus.HOLD_ACTIVE_EXPLOITATION_UNVERIFIED,
        ),
        (
            cra_input(product_scope=CraProductScope.UNKNOWN),
            CraReportabilityStatus.HOLD_PRODUCT_SCOPE_UNKNOWN,
        ),
        (
            cra_input(product_scope=CraProductScope.OUT_OF_SCOPE),
            CraReportabilityStatus.OUT_OF_SCOPE,
        ),
    )
    for value, expected in cases:
        decision = assess_cra_reportability(value)
        assert decision.status is expected
        assert decision.reportable_candidate is False
        assert decision.reporting_clock is None
        assert decision.automatic_submission_permitted is False


def test_cra_mandatory_reporting_is_not_claimed_before_11_september_2026():
    decision = assess_cra_reportability(
        cra_input(awareness_at=datetime(2026, 9, 10, 23, 59, tzinfo=UTC))
    )
    assert decision.status is CraReportabilityStatus.NOT_YET_APPLICABLE
    assert decision.reportable_candidate is False
    assert decision.reporting_clock is None


def test_severe_incident_does_not_require_active_exploitation_and_has_month_clock():
    decision = assess_cra_reportability(
        CraReportabilityInput(
            occurrence_type=CraOccurrenceType.SEVERE_INCIDENT,
            awareness_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
            company_impact=CraEvidenceState.VERIFIED,
            active_exploitation=CraEvidenceState.UNKNOWN,
            product_scope=CraProductScope.IN_SCOPE,
        )
    )
    assert decision.status is CraReportabilityStatus.HUMAN_REPORTING_REVIEW_REQUIRED
    assert decision.reporting_clock is not None
    assert decision.reporting_clock.early_warning_due_at == datetime(
        2026, 10, 1, 12, tzinfo=UTC
    )
    assert decision.reporting_clock.notification_due_at == datetime(
        2026, 10, 3, 12, tzinfo=UTC
    )
    assert decision.reporting_clock.final_report_due_at == datetime(
        2026, 11, 3, 12, tzinfo=UTC
    )
