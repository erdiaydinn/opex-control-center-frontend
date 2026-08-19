from __future__ import annotations

import pytest

from app.cyber_platform_assurance import (
    SecurityAssuranceEnvironment,
    SecurityAssurancePlan,
    SecurityAssuranceStatus,
    SecurityControlFamily,
    SecurityFindingSeverity,
    SecurityProbeMode,
    build_eay_platform_security_plan,
    record_security_assurance_finding,
)

REV = "ce1a0133ce9dcc18f17f3caa2f2ca56b11ec835c"


def test_default_eay_security_plan_covers_core_platform_invariants_without_offensive_authority() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:repo",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
    )

    assert len(plan.tests) == 12
    assert {test.control_family for test in plan.tests} == set(SecurityControlFamily)
    assert all(
        test.probe_mode is SecurityProbeMode.CONTRACT_TEST for test in plan.tests
    )
    assert all(test.destructive_actions_allowed is False for test in plan.tests)
    assert all(test.exploit_generation_allowed is False for test in plan.tests)
    assert all(test.credential_capture_allowed is False for test in plan.tests)
    assert all(test.production_mutation_allowed is False for test in plan.tests)
    assert plan.exploit_generation_allowed is False
    assert plan.production_write_allowed is False
    assert plan.automatic_remediation_allowed is False
    assert plan.execution_authority_granted is False


def test_production_assurance_plan_is_read_only_only() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:prod-read",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
        environment=SecurityAssuranceEnvironment.PRODUCTION_READ_ONLY,
    )
    assert all(
        test.probe_mode is SecurityProbeMode.AUTHORIZED_READ_ONLY
        for test in plan.tests
    )
    assert all(test.production_mutation_allowed is False for test in plan.tests)


def test_sandbox_adversarial_plan_stays_non_destructive_and_non_exploitative() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:sandbox",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
        environment=SecurityAssuranceEnvironment.SANDBOX,
    )
    assert all(
        test.probe_mode is SecurityProbeMode.SANDBOX_ADVERSARIAL
        for test in plan.tests
    )
    assert all(test.destructive_actions_allowed is False for test in plan.tests)
    assert all(test.exploit_generation_allowed is False for test in plan.tests)


def test_security_finding_is_evidence_bound_and_never_grants_remediation_authority() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:findings",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
    )

    passed = record_security_assurance_finding(
        finding_id="finding:tenant-pass",
        plan=plan,
        test_id="tenant-zero-leak",
        status=SecurityAssuranceStatus.PASS,
        severity=SecurityFindingSeverity.INFO,
        evidence_refs=("ci:tenant-zero-leak:pass",),
    )
    assert passed.control_verified is True
    assert passed.remediation_authority_granted is False
    assert passed.execution_authority_granted is False

    failed = record_security_assurance_finding(
        finding_id="finding:authz-fail",
        plan=plan,
        test_id="authz-fail-closed",
        status=SecurityAssuranceStatus.FAIL,
        severity=SecurityFindingSeverity.HIGH,
        evidence_refs=("ci:authz-boundary:failure",),
    )
    assert failed.control_verified is False


def test_security_finding_rejects_secret_bearing_evidence_reference() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:secret",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
    )
    with pytest.raises(
        ValueError,
        match="cyber_assurance_finding_unsafe_reference_forbidden",
    ):
        record_security_assurance_finding(
            finding_id="finding:unsafe",
            plan=plan,
            test_id="secret-safe-observability",
            status=SecurityAssuranceStatus.FAIL,
            severity=SecurityFindingSeverity.CRITICAL,
            evidence_refs=("authorization:bearer-material",),
        )


def test_security_finding_must_reference_test_in_exact_plan() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:membership",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
    )
    with pytest.raises(ValueError, match="cyber_assurance_finding_test_not_in_plan"):
        record_security_assurance_finding(
            finding_id="finding:unknown-test",
            plan=plan,
            test_id="not-in-plan",
            status=SecurityAssuranceStatus.INCONCLUSIVE,
            severity=SecurityFindingSeverity.MEDIUM,
            evidence_refs=("evidence:test-not-found",),
        )


def test_tampered_security_plan_cannot_enable_production_write() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:tamper",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
    )
    tampered = plan.model_copy(update={"production_write_allowed": True})
    with pytest.raises(
        ValueError,
        match="cyber_assurance_plan_production_write_forbidden",
    ):
        SecurityAssurancePlan.model_validate(tampered.model_dump(mode="json"))


def test_repository_plan_cannot_be_relabelled_as_production_read_only_with_active_probe_modes() -> None:
    plan = build_eay_platform_security_plan(
        plan_id="security-plan:mode-tamper",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
    )
    tampered = plan.model_copy(
        update={"environment": SecurityAssuranceEnvironment.PRODUCTION_READ_ONLY}
    )
    with pytest.raises(
        ValueError,
        match="cyber_assurance_production_plan_must_be_read_only",
    ):
        SecurityAssurancePlan.model_validate(tampered.model_dump(mode="json"))
