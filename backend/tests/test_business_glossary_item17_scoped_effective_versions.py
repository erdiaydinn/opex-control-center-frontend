from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText
from app.platform.business_glossary.resolver import GlossaryResolutionError, resolve_term

AT = datetime(2026, 8, 17, tzinfo=timezone.utc)
EFFECTIVE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _term(tenant: str, bu: str, concept: str, definition: str) -> GlossaryTerm:
    return GlossaryTerm(
        concept_id=concept,
        canonical_key="nsfr",
        scope=GlossaryScope(tenant_id=tenant, business_unit=bu, domain="operations"),
        status=GlossaryStatus.EFFECTIVE,
        version=1,
        effective_from=EFFECTIVE,
        display_name=LocalizedText(values={"tr": "NSFR", "en": "NSFR"}),
        short_definition=LocalizedText(values={"tr": definition, "en": definition}),
        aliases=["NSFR"],
        owner="semantic-governance",
    )


def _terms() -> list[GlossaryTerm]:
    return [
        _term("tenant-a", "Market", "nsfr.market", "Market tenant A definition"),
        _term("tenant-a", "QCommerce", "nsfr.qcommerce", "QCommerce tenant A definition"),
        _term("tenant-b", "Market", "nsfr.market", "Market tenant B definition"),
    ]


def test_same_acronym_resolves_to_scoped_effective_definition() -> None:
    terms = _terms()
    market_a = resolve_term(terms, tenant_id="tenant-a", query="NSFR", locale="en", business_unit="Market", domain="operations", at=AT)
    qcommerce_a = resolve_term(terms, tenant_id="tenant-a", query="NSFR", locale="en", business_unit="QCommerce", domain="operations", at=AT)
    market_b = resolve_term(terms, tenant_id="tenant-b", query="NSFR", locale="en", business_unit="Market", domain="operations", at=AT)

    assert (market_a.concept_id, market_a.definition) == ("nsfr.market", "Market tenant A definition")
    assert (qcommerce_a.concept_id, qcommerce_a.definition) == ("nsfr.qcommerce", "QCommerce tenant A definition")
    assert (market_b.concept_id, market_b.definition) == ("nsfr.market", "Market tenant B definition")
    assert market_a.scope.tenant_id == "tenant-a"
    assert market_b.scope.tenant_id == "tenant-b"


def test_cross_tenant_and_unknown_business_unit_never_fallback() -> None:
    terms = _terms()
    with pytest.raises(GlossaryResolutionError, match="no approved effective tenant"):
        resolve_term(terms, tenant_id="tenant-c", query="NSFR", locale="en", business_unit="Market", domain="operations", at=AT)
    with pytest.raises(GlossaryResolutionError, match="no approved effective tenant"):
        resolve_term(terms, tenant_id="tenant-a", query="NSFR", locale="en", business_unit="Unknown", domain="operations", at=AT)
