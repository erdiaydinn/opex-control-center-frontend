from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0056_audit_visit_manifests.py"


def test_visit_migration_has_single_parent_and_authoritative_tables() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision: str = "0055_merge_audit_parent_heads"' in source
    assert '"audit_visit_manifests"' in source
    assert '"audit_visit_notes"' in source
    assert '"visit_manifest_id"' in source
    assert '"visit_score_mode"' in source
    assert '"official_compliance_eligible"' in source
    assert '"scope_fingerprint"' in source


def test_visit_persistence_is_tenant_isolated_and_notes_are_append_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "current_setting('app.tenant_id', true)" in source
    assert "GRANT SELECT, INSERT ON TABLE audit_visit_notes" in source
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE audit_visit_notes" not in source


def test_focus_scores_cannot_be_promoted_as_official_compliance() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ck_audit_run_official_score_binding" in source
    official_binding = (
        "official_compliance_eligible IS FALSE OR "
        "visit_score_mode = 'OFFICIAL_COMPLIANCE'"
    )
    assert official_binding in source
    assert "ix_audit_runs_official_compliance" in source
    assert "uq_audit_run_visit_manifest" in source


def test_people_visits_are_no_score_by_database_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ck_audit_people_visit_no_score" in source
    assert "visit_type = 'PEOPLE_VISIT' OR program_key IS NOT NULL" in source
    assert "score_mode = 'NO_SCORE'" in source
