from datetime import date

import pytest
from fastapi import HTTPException

from app.company_knowledge import ApprovalRequest, CompanyKnowledgeStore, CompanyPolicyCreate
from app.grounded_chat import (
    _enforce_grounded_retrieval_truth_boundary,
    _model_backend_unavailable,
    _provenance_for_evidence,
)
from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_knowledge import LegalKnowledgeIndexer
from app.legal_verification import LegalVerificationStore, VerificationCreate
from app.main import ChatRequest


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
    authoritative_text = (
        "1 Ağustos 2026 Resmî Gazete Sayı : 99991\n"
        + ("MADDE 1\nTest mevzuat metni ve yükümlülük açıklaması.\n\n" * 8)
    )
    record = verification.create(
        VerificationCreate(
            instrument_id="tgk-x",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/08/test.htm",
            authoritative_text=authoritative_text,
            publication_date=date(2026, 8, 1),
            effective_from=date(2026, 8, 1),
            official_gazette_number="99991",
        )
    )
    verification.verify_and_apply(record.id, "checked", human_approval_ref="LEGAL-TEST-001")
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


def test_production_blocks_company_retrieval_without_central_tenant_authority(
    monkeypatch,
):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")
    request = ChatRequest(
        message="What is our cold chain policy?",
        layers=["company"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_grounded_retrieval_truth_boundary(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == (
        "tenant_scoped_retrieval_not_production_ready"
    )
    assert exc_info.value.detail["layers"] == ["company"]


def test_production_blocks_operational_retrieval_without_tenant_authority(
    monkeypatch,
):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")
    request = ChatRequest(
        message="Show current picking guidance",
        layers=["operational"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_grounded_retrieval_truth_boundary(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["layers"] == ["operational"]


def test_production_allows_global_legal_and_standard_retrieval(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")
    request = ChatRequest(
        message="What regulation applies?",
        layers=["legal", "standard"],
    )

    _enforce_grounded_retrieval_truth_boundary(request)


def test_invalid_environment_fails_closed(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "prod-ish")
    request = ChatRequest(
        message="What regulation applies?",
        layers=["legal"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_grounded_retrieval_truth_boundary(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Grounded retrieval environment is invalid"


def test_model_backend_failure_is_sanitized():
    error = _model_backend_unavailable()

    assert error.status_code == 503
    assert error.detail == {
        "error": "grounded_model_unavailable",
        "message": "Grounded answer generation is temporarily unavailable",
    }
    serialized = str(error.detail)
    assert "localhost" not in serialized
    assert "token" not in serialized.lower()
    assert "stack" not in serialized.lower()
