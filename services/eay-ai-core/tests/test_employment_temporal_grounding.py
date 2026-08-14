from datetime import date

from app.employment_intelligence import (
    EmploymentIntelligenceStore,
    EmploymentResolutionRequest,
    EmploymentRuleApproval,
    EmploymentRuleCreate,
)
from app.employment_temporal_grounding import (
    EmploymentLegalBindingCreate,
    EmploymentLegalBindingRegistry,
)
from app.legal_engine import LegalEngine, LegalInstrumentUpsert, LegalRequirementUpsert


def _setup_verified_law(db_path):
    legal = LegalEngine(db_path)
    legal.upsert_instrument(LegalInstrumentUpsert(
        id="law-4857-test",
        title="4857 İş Kanunu test instrument",
        instrument_type="law",
        publication_date=date(2003, 6, 10),
        effective_from=date(2003, 6, 10),
        source_url="https://www.mevzuat.gov.tr/example-4857",
        verification_status="verified",
        topics=["employment"],
    ))
    legal.upsert_requirement(LegalRequirementUpsert(
        id="req-weekly-hours-test",
        authority="legal",
        source_id="law-4857-test",
        scope="employee",
        dimension="weekly_working_time",
        operator="<=",
        numeric_value=45,
        unit="hours_week",
        effective_from=date(2003, 6, 10),
        citation="4857 test citation",
    ))


def _approve_employment_law(db_path):
    store = EmploymentIntelligenceStore(db_path)
    created = store.create(EmploymentRuleCreate(
        rule_id="weekly-working-time",
        kind="labor_law",
        title="Weekly working time",
        version="1",
        statement="Weekly working time legal baseline is grounded to the reviewed requirement.",
        source_url="https://www.mevzuat.gov.tr/example-4857",
        effective_from=date(2003, 6, 10),
    ))
    return store.approve(created.id, EmploymentRuleApproval(
        approved_by="legal-reviewer",
        approval_reference="LEGAL-HR-001",
    ))


def test_binding_law_employment_answer_requires_exact_legal_binding(tmp_path):
    db_path = tmp_path / "eay.db"
    _setup_verified_law(db_path)
    _approve_employment_law(db_path)
    registry = EmploymentLegalBindingRegistry(db_path)
    result = registry.resolve(EmploymentResolutionRequest(
        question_kind="labor_law",
        as_of=date(2026, 8, 12),
    ))
    assert not result.resolved
    assert "employment_grounding_binding_missing:weekly-working-time" in result.blockers


def test_bound_employment_rule_resolves_only_when_instrument_is_temporally_active(tmp_path):
    db_path = tmp_path / "eay.db"
    _setup_verified_law(db_path)
    rule = _approve_employment_law(db_path)
    registry = EmploymentLegalBindingRegistry(db_path)
    binding = registry.create(EmploymentLegalBindingCreate(
        employment_rule_record_id=rule.id,
        legal_instrument_id="law-4857-test",
        legal_requirement_ids=["req-weekly-hours-test"],
        reviewed_by="legal-reviewer",
        approval_reference="EMPLOYMENT-BIND-001",
    ))
    result = registry.resolve(EmploymentResolutionRequest(
        question_kind="labor_law",
        as_of=date(2026, 8, 12),
    ))
    assert result.resolved
    assert result.legal_binding_fingerprints == (binding.fingerprint,)
    assert "law-4857-test" in result.active_legal_instrument_ids
    assert result.legal_temporal_resolution_fingerprint is not None


def test_binding_rejects_requirement_from_different_instrument(tmp_path):
    db_path = tmp_path / "eay.db"
    _setup_verified_law(db_path)
    legal = LegalEngine(db_path)
    legal.upsert_instrument(LegalInstrumentUpsert(
        id="other-law",
        title="Other verified law",
        instrument_type="law",
        publication_date=date(2020, 1, 1),
        effective_from=date(2020, 1, 1),
        source_url="https://www.mevzuat.gov.tr/example-other",
        verification_status="verified",
    ))
    legal.upsert_requirement(LegalRequirementUpsert(
        id="other-req",
        authority="legal",
        source_id="other-law",
        scope="employee",
        dimension="other",
        operator="required",
        effective_from=date(2020, 1, 1),
        citation="other",
    ))
    rule = _approve_employment_law(db_path)
    registry = EmploymentLegalBindingRegistry(db_path)
    try:
        registry.create(EmploymentLegalBindingCreate(
            employment_rule_record_id=rule.id,
            legal_instrument_id="law-4857-test",
            legal_requirement_ids=["other-req"],
            reviewed_by="legal-reviewer",
            approval_reference="EMPLOYMENT-BIND-002",
        ))
        assert False, "expected source mismatch"
    except ValueError as exc:
        assert str(exc) == "employment_legal_binding_requirement_source_mismatch"
