from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_audit_intelligence_metrics_are_server_deterministic() -> None:
    source = (ROOT / "app/modules/audit/intelligence.py").read_text(encoding="utf-8")
    assert '"llm_computed_metrics": False' in source
    assert '"calculation_version": "audit.intelligence.summary.v2"' in source
    assert "audit_runs" in source
    assert "audit_actions" in source
    assert "audit_assurance_cases" in source
    assert "receipt_fingerprint" in source


def test_official_compliance_score_excludes_focus_visit_scores() -> None:
    source = (ROOT / "app/modules/audit/intelligence.py").read_text(encoding="utf-8")
    assert "official_compliance_eligible IS TRUE" in source
    assert '"official_compliance_only": True' in source
    assert '"eligibility_column": "audit_runs.official_compliance_eligible"' in source
    assert '"non_official_score_modes": ["FOCUS_SCORE"]' in source
    assert "FROM official_scored_runs" in source


def test_evidence_coverage_requires_server_privacy_verification() -> None:
    source = (ROOT / "app/modules/audit/intelligence.py").read_text(encoding="utf-8")
    assert "audit_redaction_verification_events" in source
    assert "verification_status = 'verified'" in source
    assert "evidence_coverage_percent" in source
    assert "privacy_verified_media_runs" in source


def test_repeat_findings_are_derived_from_multiple_runs_at_same_location() -> None:
    source = (ROOT / "app/modules/audit/intelligence.py").read_text(encoding="utf-8")
    assert "GROUP BY sr.location_id, aa.item_key" in source
    assert "COUNT(DISTINCT aa.audit_run_id) >= 2" in source


def test_intelligence_route_requires_analytics_permission() -> None:
    source = (ROOT / "app/modules/audit/intelligence_routes.py").read_text(encoding="utf-8")
    assert 'prefix="/v1/audit/intelligence"' in source
    assert 'require_audit_scope(principal, "feature:audit:analytics")' in source
    assert 'router.get("/summary")' in source


def test_intelligence_route_is_composed_into_platform_asgi() -> None:
    source = (ROOT / "app/budget_main.py").read_text(encoding="utf-8")
    assert "audit_intelligence_router" in source
    assert "app.include_router(audit_intelligence_router)" in source
