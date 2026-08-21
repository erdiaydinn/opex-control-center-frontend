from datetime import date

import pytest

from app.company_knowledge import ApprovalRequest, CompanyKnowledgeStore, CompanyPolicyCreate
from app.main import Store


def policy(version: str, effective_from: date, content: str = "Depo soguk zincir standardi 4 C altinda tutulmalidir."):
    return CompanyPolicyCreate(
        policy_id="cold-chain-sop",
        company="EAY-Test",
        title="Cold Chain SOP",
        version=version,
        content=content,
        effective_from=effective_from,
        owner="Quality",
    )


def test_draft_cannot_enter_company_rag(tmp_path):
    db = tmp_path / "eay.db"
    Store(db)  # creates shared knowledge tables/FTS
    store = CompanyKnowledgeStore(db)
    record = store.create(policy("1.0", date(2026, 1, 1)))

    with pytest.raises(ValueError, match="only approved"):
        store.index_approved(record.id)


def test_approved_policy_is_indexed_and_retrievable(tmp_path):
    db = tmp_path / "eay.db"
    rag = Store(db)
    store = CompanyKnowledgeStore(db)
    record = store.create(policy("1.0", date(2026, 1, 1)))
    approved = store.approve(
        record.id,
        ApprovalRequest(approved_by="quality-lead", approval_reference="QA-2026-001"),
    )
    assert approved.status == "approved"
    assert store.index_approved(record.id) == 1

    hits = rag.search(
        "soguk zincir standardi",
        as_of=date(2026, 2, 1),
        layers=["company"],
        limit=5,
    )
    assert hits
    assert hits[0].layer == "company"
    assert hits[0].authority_level == "company"
    assert "Cold Chain SOP" in hits[0].title


def test_new_approved_version_supersedes_old_version_temporally(tmp_path):
    db = tmp_path / "eay.db"
    Store(db)
    store = CompanyKnowledgeStore(db)

    old = store.create(policy("1.0", date(2026, 1, 1)))
    store.approve(old.id, ApprovalRequest(approved_by="qa", approval_reference="A1"))

    new = store.create(policy("2.0", date(2026, 7, 1), "Yeni soguk zincir standardi 3 C altinda tutulmalidir."))
    store.approve(new.id, ApprovalRequest(approved_by="qa", approval_reference="A2"))

    before = store.list_as_of("EAY-Test", date(2026, 6, 30))
    after = store.list_as_of("EAY-Test", date(2026, 7, 1))

    assert [item.version for item in before] == ["1.0"]
    assert [item.version for item in after] == ["2.0"]


def test_approval_requires_effective_date(tmp_path):
    db = tmp_path / "eay.db"
    Store(db)
    store = CompanyKnowledgeStore(db)
    record = store.create(
        CompanyPolicyCreate(
            policy_id="audit-sop",
            company="EAY-Test",
            title="Audit SOP",
            version="1.0",
            content="This is a sufficiently long internal audit procedure text.",
        )
    )
    with pytest.raises(ValueError, match="effective_from"):
        store.approve(record.id, ApprovalRequest(approved_by="qa", approval_reference="A3"))
