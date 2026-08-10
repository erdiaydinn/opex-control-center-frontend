from datetime import date

from app.company_knowledge import ApprovalRequest, CompanyKnowledgeStore, CompanyPolicyCreate
from app.grounded_chat import _provenance_for_evidence
from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_knowledge import LegalKnowledgeStore
from app.legal_verification import LegalVerificationStore, VerificationCreate


def test_provenance_resolves_company_policy(tmp_path, monkeypatch):
    db = tmp_path / "eay.db"
    monkeypatch.setenv("EAY_AI_DB_PATH", str(db))

    # Initialize base knowledge tables through main Store lazily by importing here.
    from app.main import Store
    Store(db)

    company = CompanyKnowledgeStore(db)
    policy = company.create(
        CompanyPolicyCreate(
            policy_id="cold-chain",
            company="EAY",
            title="Cold Chain SOP",
            version="2.0",
            content="Chilled receiving process temperature control and escalation." * 2,
            effective_from=date(2026, 8, 1),
        )
    )
    company.approve(policy.id, ApprovalRequest(approved_by="ops", approval_reference="APR-1"))
    company.index_approved(policy.id, chunk_size=100)

    # Patch module DB path for provenance lookup.
    import app.grounded_chat as gc
    gc.DB_PATH = db
    items = _provenance_for_evidence([f"company:{policy.id}:0"])
    assert len(items) == 1
    assert items[0].layer == "company"
    assert items[0].source_id == "cold-chain"
    assert items[0].version == "2.0"
    assert items[0].content_sha256


def test_provenance_resolves_verified_legal_chunk(tmp_path, monkeypatch):
    db = tmp_path / "eay.db"
    monkeypatch.setenv("EAY_AI_DB_PATH", str(db))
    from app.main import Store
    Store(db)

    engine = LegalEngine(db)
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="tgk-x",
            title="Test Regulation",
            instrument_type="regulation",
            source_url="https://www.resmigazete.gov.tr/eskiler/2026/08/test.htm",
            verification_status="draft",
        )
    )
    verification = LegalVerificationStore(db)
    record = verification.create(
        VerificationCreate(
            instrument_id="tgk-x",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/08/test.htm",
            authoritative_text="Madde 1 test mevzuat metni. " * 8,
            publication_date=date(2026, 8, 1),
            effective_from=date(2026, 8, 1),
        )
    )
    verification.decide(record.id, "verified", "checked")
    # Promote instrument through engine to verified for legal knowledge indexing.
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="tgk-x",
            title="Test Regulation",
            instrument_type="regulation",
            publication_date=date(2026, 8, 1),
            effective_from=date(2026, 8, 1),
            source_url="https://www.resmigazete.gov.tr/eskiler/2026/08/test.htm",
            verification_status="verified",
        )
    )
    legal_knowledge = LegalKnowledgeStore(db)
    count = legal_knowledge.index_verified(record.id, chunk_size=100)
    assert count >= 1

    import app.grounded_chat as gc
    gc.DB_PATH = db
    items = _provenance_for_evidence([f"legal:{record.id}:0"])
    assert len(items) == 1
    assert items[0].layer == "legal"
    assert items[0].source_id == "tgk-x"
    assert items[0].verification_id == record.id
    assert items[0].content_sha256
    assert items[0].chunk_sha256
