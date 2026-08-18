from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/0044_external_acceptance_evidence.py"


def test_external_evidence_ledger_is_append_only_rls_and_runtime_read_only() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "0044_external_acceptance_evidence",
        "0043_shared_platform_delivery_search",
        "FORCE ROW LEVEL SECURITY",
        "external acceptance evidence is append-only",
        "GRANT SELECT ON external_acceptance_evidence",
        "REVOKE INSERT, UPDATE, DELETE ON external_acceptance_evidence",
        "roadmap_item BETWEEN 49 AND 55",
    ):
        assert token in text
    assert "'REPOSITORY'" not in text
    assert "'SYNTHETIC'" not in text
