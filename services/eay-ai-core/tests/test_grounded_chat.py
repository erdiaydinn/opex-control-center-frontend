from datetime import date

from app.company_knowledge import ApprovalRequest, CompanyKnowledgeStore, CompanyPolicyCreate
from app.grounded_chat import _provenance_for_evidence
from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_knowledge import LegalKnowledgeIndexer
from app.legal_verification import LegalVerificationStore, VerificationCreate


def test_provenance_resolves_company_policy(tmp_path):
    db = tmp_path / "eay.db"
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

    import app.grounded_chat as gc
    gc.DB_PATH = db
    items = _provenance_for_evidence([f"company:{policy.id}:0"])
    assert len(items) == 1
    assert items[0].layer == "company"
    assert items[0].source_id == "cold-chain"
    assert items[0].version == "2.0"
    assert items[0].content_sha256


def test_provenance_resolves_verified_legal_chunk(tmp_path):
    db = tmp_path / "eay.db"
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
            authoritative_text=("MADDE 1\nTest mevzuat metni ve yükümlülük açıklaması.\n\n" * 8),
            publication_date=date(2026, 8, 1),
            effective_from=date(2026, 8, 1),
        )
    )
    verification.decide(record.id, "verified", "checked")
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
    indexer = LegalKnowledgeIndexer(db)
    chunks = indexer.sync_verified("tgk-x")
    assert chunks

    import app.grounded_chat as gc
    gc.DB_PATH = db
    items = _provenance_for_evidence([chunks[0].id])
    assert len(items) == 1
    assert items[0].layer == "legal"
    assert items[0].source_id == "tgk-x"
    assert items[0].verification_id == record.id
    assert items[0].content_sha256
    assert items[0].chunk_sha256
