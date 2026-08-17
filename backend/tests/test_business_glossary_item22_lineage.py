from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.lineage import (
    GlossaryLineageAssetKind,
    GlossaryLineageBinding,
    GlossaryLineageError,
    GlossaryLineageRelation,
    lineage_for_answer,
)
from app.platform.business_glossary.models import GlossaryAnswer, GlossaryScope


def _answer(*, tenant: str = "tenant-a", version: int = 2, authoritative: bool = True) -> GlossaryAnswer:
    return GlossaryAnswer(
        concept_id="nsfr",
        canonical_key="nsfr",
        locale="en",
        display_name="NSFR",
        definition="Net Service Failure Rate",
        formula="PFR + Refund + Compensation",
        unit="percent",
        data_source_refs=["curated_data_shared.orders"],
        scope=GlossaryScope(tenant_id=tenant, country="TR", business_unit="Market", domain="operations"),
        version=version,
        authoritative=authoritative,
    )


def _binding(tenant: str, version: int, kind: GlossaryLineageAssetKind, relation: GlossaryLineageRelation, ref: str):
    return GlossaryLineageBinding(
        tenant_id=tenant,
        concept_id="nsfr",
        glossary_version=version,
        asset_kind=kind,
        relation=relation,
        asset_ref=ref,
    )


def test_page_ready_lineage_uses_only_exact_authoritative_version_and_tenant() -> None:
    bindings = [
        _binding("tenant-a", 2, GlossaryLineageAssetKind.DATASET, GlossaryLineageRelation.SOURCE, "curated_data_shared.orders"),
        _binding("tenant-a", 2, GlossaryLineageAssetKind.API_FIELD, GlossaryLineageRelation.EXPOSED_AS, "GET /api/kpis/nsfr:data.value"),
        _binding("tenant-a", 2, GlossaryLineageAssetKind.DASHBOARD, GlossaryLineageRelation.USED_BY, "ops-overview:NSFR"),
        _binding("tenant-a", 1, GlossaryLineageAssetKind.DATASET, GlossaryLineageRelation.SOURCE, "legacy.nsfr.v1"),
        _binding("tenant-b", 2, GlossaryLineageAssetKind.DASHBOARD, GlossaryLineageRelation.USED_BY, "tenant-b-secret"),
    ]

    view = lineage_for_answer(_answer(), bindings)

    assert view.tenant_id == "tenant-a"
    assert view.concept_id == "nsfr"
    assert view.glossary_version == 2
    assert [item.asset_ref for item in view.source_datasets] == ["curated_data_shared.orders"]
    assert [item.asset_ref for item in view.api_fields] == ["GET /api/kpis/nsfr:data.value"]
    assert [item.asset_ref for item in view.dashboards] == ["ops-overview:NSFR"]
    assert all(item.glossary_version == 2 for item in view.source_datasets + view.api_fields + view.dashboards)
    assert all(item.tenant_id == "tenant-a" for item in view.source_datasets + view.api_fields + view.dashboards)


def test_no_lineage_is_truthful_empty_view_not_invented_usage() -> None:
    view = lineage_for_answer(_answer(), [])
    assert view.source_datasets == []
    assert view.api_fields == []
    assert view.dashboards == []
    assert view.authoritative is True


def test_non_authoritative_answer_cannot_claim_lineage() -> None:
    with pytest.raises(GlossaryLineageError, match="authoritative"):
        lineage_for_answer(_answer(authoritative=False), [])


def test_asset_kind_relation_pairs_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="invalid lineage relation"):
        _binding("tenant-a", 2, GlossaryLineageAssetKind.DATASET, GlossaryLineageRelation.USED_BY, "wrong")
