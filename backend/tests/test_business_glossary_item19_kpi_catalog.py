from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText
from app.platform.business_glossary.semantic_consumers import SemanticAuthorityUnavailable, resolve_for_kpi_catalog

AT = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _term(*, status: GlossaryStatus, version: int, formula: str | None, sources: list[str], effective_from=None, effective_to=None) -> GlossaryTerm:
    return GlossaryTerm(
        concept_id="tenant-a-nsfr",
        canonical_key="nsfr",
        scope=GlossaryScope(tenant_id="tenant-a", country="TR", business_unit="Market", domain="operations"),
        status=status,
        version=version,
        effective_from=effective_from,
        effective_to=effective_to,
        display_name=LocalizedText(values={"tr": "NSFR", "en": "NSFR"}),
        short_definition=LocalizedText(values={"tr": "Net Sipariş Hata Oranı", "en": "Net Service Failure Rate"}),
        aliases=["NSFR"],
        formula=formula,
        unit="percent",
        data_source_refs=sources,
        owner="semantic-governance",
    )


def _resolve(terms: list[GlossaryTerm]):
    return resolve_for_kpi_catalog(
        terms,
        tenant_id="tenant-a",
        query="NSFR",
        locale="tr",
        country="TR",
        business_unit="Market",
        domain="operations",
        at=AT,
    )


def test_nsfr_formula_and_sources_are_bound_to_same_current_effective_version() -> None:
    effective_v1 = _term(
        status=GlossaryStatus.EFFECTIVE,
        version=1,
        formula="PFR + Refund + Compensation",
        sources=["curated_data_shared.orders", "ops.nsfr_adjustments.v1"],
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer_draft_v2 = _term(
        status=GlossaryStatus.DRAFT,
        version=2,
        formula="PFR + Refund",
        sources=["ops.nsfr_adjustments.v2"],
    )

    answer = _resolve([effective_v1, newer_draft_v2])

    assert answer.version == 1
    assert answer.formula == "PFR + Refund + Compensation"
    assert answer.data_source_refs == ["curated_data_shared.orders", "ops.nsfr_adjustments.v1"]
    assert answer.authoritative is True


def test_superseded_formula_cannot_leak_into_new_effective_kpi_version() -> None:
    superseded_v1 = _term(
        status=GlossaryStatus.SUPERSEDED,
        version=1,
        formula="old formula",
        sources=["legacy.nsfr.v1"],
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    effective_v2 = _term(
        status=GlossaryStatus.EFFECTIVE,
        version=2,
        formula="PFR + Refund + Compensation - ApprovedExclusions",
        sources=["curated_data_shared.orders", "ops.nsfr_adjustments.v2"],
        effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    answer = _resolve([superseded_v1, effective_v2])

    assert answer.version == 2
    assert answer.formula == "PFR + Refund + Compensation - ApprovedExclusions"
    assert answer.data_source_refs == ["curated_data_shared.orders", "ops.nsfr_adjustments.v2"]


@pytest.mark.parametrize(
    ("formula", "sources", "message"),
    [
        (None, ["curated_data_shared.orders"], "no governed formula"),
        ("PFR + Refund + Compensation", [], "no governed data source binding"),
        ("PFR + Refund + Compensation", [""], "invalid data source binding"),
    ],
)
def test_incomplete_effective_kpi_catalog_entries_fail_closed(formula, sources, message) -> None:
    incomplete = _term(
        status=GlossaryStatus.EFFECTIVE,
        version=1,
        formula=formula,
        sources=sources,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(SemanticAuthorityUnavailable, match=message):
        _resolve([incomplete])
