from datetime import UTC, datetime

from app.enterprise_domain_admission import (
    DomainAnswerRequest,
    DomainEvidence,
    DomainRisk,
    admit_domain_answer,
)
from app.enterprise_domain_registry import EnterpriseDomain, SourceAuthority

NOW = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
FP = "a" * 64


def ev(ref, authority, *, tenant="tenant-a", authoritative=True, observed=NOW):
    return DomainEvidence(
        evidence_ref=ref,
        authority=authority,
        observed_at=observed,
        tenant_id=tenant,
        source_fingerprint=FP,
        authoritative=authoritative,
    )


def req(domain, *, risk=DomainRisk.LOW, **changes):
    values = {
        "request_id": "request-1",
        "tenant_id": "tenant-a",
        "domain": domain,
        "as_of": NOW,
        "risk": risk,
    }
    values.update(changes)
    return DomainAnswerRequest(**values)


def test_critical_labor_answer_requires_all_authorities_critic_and_human_approval():
    evidence = (
        ev("law", SourceAuthority.BINDING_LAW),
        ev("guidance", SourceAuthority.OFFICIAL_GUIDANCE),
        ev("policy", SourceAuthority.COMPANY_POLICY),
    )
    blocked = admit_domain_answer(
        req(
            EnterpriseDomain.PAYROLL_LABOR_LAW,
            risk=DomainRisk.CRITICAL,
            deterministic_result_fingerprint="b" * 64,
        ),
        evidence,
    )
    assert blocked.decision_ready is False
    assert "independent_domain_critic_required" in blocked.blockers
    assert "critical_domain_human_approval_required" in blocked.blockers

    ready = admit_domain_answer(
        req(
            EnterpriseDomain.PAYROLL_LABOR_LAW,
            risk=DomainRisk.CRITICAL,
            deterministic_result_fingerprint="b" * 64,
            independent_critic_receipt_ref="critic://legal/1",
            human_approval_ref="approval://legal/1",
        ),
        evidence,
    )
    assert ready.decision_ready is True
    assert ready.execution_authority_granted is False


def test_finance_answer_fails_closed_without_deterministic_receipt_and_law():
    result = admit_domain_answer(
        req(EnterpriseDomain.FINANCE_ACCOUNTING),
        (ev("policy", SourceAuthority.COMPANY_POLICY),),
    )
    assert result.decision_ready is False
    assert "required_authority_missing:binding_law" in result.blockers
    assert "required_authority_missing:official_guidance" in result.blockers
    assert "deterministic_result_evidence_required" in result.blockers


def test_cross_tenant_future_and_unverified_evidence_never_satisfy_authority():
    result = admit_domain_answer(
        req(EnterpriseDomain.PEOPLE_HR, contains_employee_data=True),
        (
            ev("policy", SourceAuthority.COMPANY_POLICY, tenant="tenant-b"),
            ev("employee", SourceAuthority.EMPLOYEE_RECORD, authoritative=False),
        ),
    )
    assert result.decision_ready is False
    assert "cross_tenant_evidence:policy" in result.blockers
    assert "evidence_not_authoritative:employee" in result.blockers


def test_operations_domain_rejects_employee_personalization_and_missing_company_truth():
    result = admit_domain_answer(
        req(
            EnterpriseDomain.RETAIL_OPERATIONS,
            contains_employee_data=True,
            deterministic_result_fingerprint="c" * 64,
        ),
        (ev("ops", SourceAuthority.GOVERNED_OPERATIONAL_DATA),),
    )
    assert result.decision_ready is False
    assert "required_authority_missing:company_policy" in result.blockers
    assert "employee_personalization_forbidden_for_domain" in result.blockers


def test_admission_fingerprint_is_stable_but_changes_with_evidence_lineage():
    request = req(
        EnterpriseDomain.ECONOMICS_MARKET,
        deterministic_result_fingerprint="d" * 64,
    )
    first = admit_domain_answer(
        request,
        (
            ev("official", SourceAuthority.OFFICIAL_ECONOMIC_DATA),
            ev("ops", SourceAuthority.GOVERNED_OPERATIONAL_DATA),
        ),
    )
    reordered = admit_domain_answer(
        request,
        (
            ev("ops", SourceAuthority.GOVERNED_OPERATIONAL_DATA),
            ev("official", SourceAuthority.OFFICIAL_ECONOMIC_DATA),
        ),
    )
    changed = admit_domain_answer(
        request,
        (
            ev("official", SourceAuthority.OFFICIAL_ECONOMIC_DATA),
            DomainEvidence(
                evidence_ref="ops",
                authority=SourceAuthority.GOVERNED_OPERATIONAL_DATA,
                observed_at=NOW,
                tenant_id="tenant-a",
                source_fingerprint="e" * 64,
            ),
        ),
    )
    assert first.decision_ready is True
    assert first.admission_fingerprint == reordered.admission_fingerprint
    assert first.admission_fingerprint != changed.admission_fingerprint
