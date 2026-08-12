from datetime import date

import pytest

from app.employment_intelligence import (
    EmployeeContext,
    EmploymentIntelligenceStore,
    EmploymentResolutionRequest,
    EmploymentRuleApproval,
    EmploymentRuleCreate,
)


def _approve(store, payload):
    created = store.create(payload)
    return store.approve(created.id, EmploymentRuleApproval(approved_by="hr-reviewer", approval_reference="HR-2026-001"))


def test_payroll_rule_requires_official_source_and_deterministic_calculation(tmp_path):
    store = EmploymentIntelligenceStore(tmp_path / "eay.db")
    with pytest.raises(ValueError, match="employment_rule_official_source_required"):
        store.create(EmploymentRuleCreate(
            rule_id="payroll-tax",
            kind="payroll",
            title="Payroll tax",
            version="2026",
            statement="Current payroll tax rule for governed calculation.",
            effective_from=date(2026, 1, 1),
            deterministic_calculation_id="tr-payroll-2026",
        ))
    with pytest.raises(ValueError, match="employment_payroll_calculation_contract_required"):
        EmploymentRuleCreate(
            rule_id="payroll-tax",
            kind="payroll",
            title="Payroll tax",
            version="2026",
            statement="Current payroll tax rule for governed calculation.",
            source_url="https://www.gib.gov.tr/vergi-konulari/1_bireysel/11_ucret_geliri/11",
            effective_from=date(2026, 1, 1),
        )


def test_unapproved_rule_never_resolves(tmp_path):
    store = EmploymentIntelligenceStore(tmp_path / "eay.db")
    store.create(EmploymentRuleCreate(
        rule_id="labor-4857",
        kind="labor_law",
        title="Employment law source",
        version="2026",
        statement="Verified legal statement placeholder for test purposes.",
        source_url="https://www.mevzuat.gov.tr/example",
        effective_from=date(2026, 1, 1),
    ))
    result = store.resolve(EmploymentResolutionRequest(question_kind="labor_law", as_of=date(2026, 8, 12)))
    assert "employment_resolution_verified_official_rule_missing" in result.blockers
    assert result.legal_rule_fingerprints == ()


def test_payroll_resolution_separates_official_and_company_evidence(tmp_path):
    store = EmploymentIntelligenceStore(tmp_path / "eay.db")
    official = _approve(store, EmploymentRuleCreate(
        rule_id="sgk-premium",
        kind="payroll",
        title="SGK premium contract",
        version="2026",
        statement="Use the reviewed SGK premium parameters for deterministic payroll calculation.",
        source_url="https://www.sgk.gov.tr/Content/Post/example",
        effective_from=date(2026, 1, 1),
        deterministic_calculation_id="tr-sgk-premium-2026",
    ))
    result = store.resolve(EmploymentResolutionRequest(question_kind="payroll", as_of=date(2026, 8, 12)))
    assert result.blockers == ()
    assert official.fingerprint in result.legal_rule_fingerprints
    assert result.company_rule_fingerprints == ()
    assert result.deterministic_calculation_ids == ("tr-sgk-premium-2026",)


def test_benefit_resolution_requires_company_and_employee_scope(tmp_path):
    store = EmploymentIntelligenceStore(tmp_path / "eay.db")
    benefit = _approve(store, EmploymentRuleCreate(
        rule_id="private-health",
        kind="benefit",
        title="Private health insurance",
        version="2026.1",
        statement="Approved company private health benefit for eligible employee groups.",
        company="EAY",
        effective_from=date(2026, 1, 1),
        employee_groups=["manager"],
        locations=["TR"],
    ))
    missing = store.resolve(EmploymentResolutionRequest(question_kind="benefit", as_of=date(2026, 8, 12), company="EAY"))
    assert "employment_resolution_employee_context_required" in missing.blockers
    matched = store.resolve(EmploymentResolutionRequest(
        question_kind="benefit",
        as_of=date(2026, 8, 12),
        company="EAY",
        employee=EmployeeContext(employee_group="manager", location="TR"),
    ))
    assert matched.blockers == ()
    assert matched.company_rule_fingerprints == (benefit.fingerprint,)


def test_historical_effective_date_prevents_future_rule_leakage(tmp_path):
    store = EmploymentIntelligenceStore(tmp_path / "eay.db")
    _approve(store, EmploymentRuleCreate(
        rule_id="future-payroll",
        kind="payroll",
        title="Future payroll change",
        version="2027",
        statement="Future payroll calculation contract must not leak into 2026 answers.",
        source_url="https://www.gib.gov.tr/example",
        effective_from=date(2027, 1, 1),
        deterministic_calculation_id="tr-payroll-2027",
    ))
    result = store.resolve(EmploymentResolutionRequest(question_kind="payroll", as_of=date(2026, 8, 12)))
    assert "tr-payroll-2027" not in result.deterministic_calculation_ids
    assert "employment_resolution_verified_official_rule_missing" in result.blockers
