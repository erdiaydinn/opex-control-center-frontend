from datetime import date
from uuid import UUID

import pytest

from app.main import KnowledgeUpsert
from app.tenant_retrieval import TenantScopedKnowledgeStore

TENANT_A = UUID("00000000-0000-0000-0000-00000000a001")
TENANT_B = UUID("00000000-0000-0000-0000-00000000b001")


def knowledge(doc_id: str, layer: str, marker: str) -> KnowledgeUpsert:
    authority = {
        "company": "company",
        "operational": "operational",
        "legal": "binding",
        "standard": "voluntary",
    }[layer]
    return KnowledgeUpsert(
        id=doc_id,
        layer=layer,
        title=f"Cold chain {marker}",
        content=f"Cold chain receiving temperature control {marker} evidence.",
        source_name=f"source-{marker}",
        authority_level=authority,
        effective_from=date(2026, 1, 1),
    )


def test_tenant_scoped_query_never_returns_foreign_company_or_operational_rows(
    tmp_path,
):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    store.upsert(knowledge("company-a", "company", "tenant-a"), tenant_id=TENANT_A)
    store.upsert(knowledge("company-b", "company", "tenant-b"), tenant_id=TENANT_B)
    store.upsert(
        knowledge("operational-a", "operational", "tenant-a"),
        tenant_id=TENANT_A,
    )
    store.upsert(
        knowledge("operational-b", "operational", "tenant-b"),
        tenant_id=TENANT_B,
    )
    store.upsert(knowledge("legal-global", "legal", "global"))

    evidence = store.search(
        "cold chain receiving temperature control",
        date(2026, 8, 15),
        ["company", "operational", "legal"],
        20,
        tenant_id=TENANT_A,
    )
    ids = {item.id for item in evidence}

    assert {"company-a", "operational-a", "legal-global"} <= ids
    assert "company-b" not in ids
    assert "operational-b" not in ids


def test_tenant_scoped_query_requires_verified_tenant_uuid(tmp_path):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    store.upsert(knowledge("company-a", "company", "tenant-a"), tenant_id=TENANT_A)

    with pytest.raises(
        ValueError,
        match="tenant_id_required_for_tenant_scoped_retrieval",
    ):
        store.search(
            "cold chain",
            date(2026, 8, 15),
            ["company"],
            10,
        )


def test_legacy_unscoped_tenant_rows_are_fail_closed(tmp_path):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    store.store.upsert_knowledge(knowledge("legacy-company", "company", "legacy"))
    store.upsert(knowledge("company-a", "company", "tenant-a"), tenant_id=TENANT_A)

    evidence = store.search(
        "cold chain",
        date(2026, 8, 15),
        ["company"],
        10,
        tenant_id=TENANT_A,
    )
    ids = {item.id for item in evidence}

    assert "company-a" in ids
    assert "legacy-company" not in ids


def test_global_knowledge_rejects_tenant_binding(tmp_path):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")

    with pytest.raises(ValueError, match="global_knowledge_must_not_be_tenant_scoped"):
        store.upsert(knowledge("legal-a", "legal", "global"), tenant_id=TENANT_A)


def test_same_document_id_cannot_be_rehomed_to_another_tenant(tmp_path):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    store.upsert(
        knowledge("shared-company-id", "company", "tenant-a-original"),
        tenant_id=TENANT_A,
    )

    with pytest.raises(
        ValueError,
        match="tenant_scoped_document_identity_collision:shared-company-id",
    ):
        store.upsert(
            knowledge("shared-company-id", "company", "tenant-b-overwrite"),
            tenant_id=TENANT_B,
        )

    tenant_a = store.search(
        "tenant-a-original",
        date(2026, 8, 16),
        ["company"],
        10,
        tenant_id=TENANT_A,
    )
    tenant_b = store.search(
        "tenant-a-original",
        date(2026, 8, 16),
        ["company"],
        10,
        tenant_id=TENANT_B,
    )

    assert [item.id for item in tenant_a] == ["shared-company-id"]
    assert tenant_a[0].source_name == "source-tenant-a-original"
    assert tenant_b == []


def test_legacy_unscoped_tenant_id_cannot_be_silently_claimed(tmp_path):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    store.store.upsert_knowledge(knowledge("legacy-shared", "company", "legacy"))

    with pytest.raises(
        ValueError,
        match="tenant_scoped_document_identity_collision:legacy-shared",
    ):
        store.upsert(
            knowledge("legacy-shared", "company", "tenant-a"),
            tenant_id=TENANT_A,
        )


def test_global_document_cannot_overwrite_tenant_scoped_identity(tmp_path):
    store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    store.upsert(
        knowledge("shared-id", "company", "tenant-a"),
        tenant_id=TENANT_A,
    )

    with pytest.raises(ValueError, match="global_document_identity_collision:shared-id"):
        store.upsert(knowledge("shared-id", "legal", "global-overwrite"))
