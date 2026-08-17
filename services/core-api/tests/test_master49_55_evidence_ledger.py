from pathlib import Path


def test_external_evidence_ledger_is_append_only_rls_and_runtime_read_only():
    text=(Path(__file__).resolve().parents[1]/'alembic/versions/0049_external_acceptance_evidence.py').read_text()
    for token in ('FORCE ROW LEVEL SECURITY','external acceptance evidence is append-only','GRANT SELECT ON external_acceptance_evidence','REVOKE INSERT,UPDATE,DELETE ON external_acceptance_evidence',"CHECK(roadmap_item BETWEEN 49 AND 55)"):
        assert token in text
    assert "'REPOSITORY'" not in text and "'SYNTHETIC'" not in text
