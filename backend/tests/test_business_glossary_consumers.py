from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.models import (
    GlossaryScope,
    GlossaryStatus,
    GlossaryTerm,
    LocalizedText,
)
from app.platform.business_glossary.semantic_consumers import (
    SemanticAuthorityUnavailable,
    resolve_for_academy,
    resolve_for_help,
    resolve_for_insight,
    resolve_for_jarvis,
)


def term() -> GlossaryTerm:
    return GlossaryTerm(
        concept_id="tenant-a-nsfr-v3",
        canonical_key="nsfr",
        scope=GlossaryScope(tenant_id="tenant-a", country="TR", domain="operations"),
        status=GlossaryStatus.EFFECTIVE,
        version=3,
        effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        display_name=LocalizedText(values={"tr": "NSFR", "en": "NSFR"}),
        short_definition=LocalizedText(values={"tr": "Onaylı tanım", "en": "Approved definition"}),
        formula="PFR + Refund + Compensation",
        unit="percent",
        owner="ops-excellence",
    )


def kwargs() -> dict[str, object]:
    return {
        "tenant_id": "tenant-a",
        "country": "TR",
        "domain": "operations",
        "query": "NSFR",
        "locale": "tr",
        "at": datetime(2026, 8, 17, tzinfo=timezone.utc),
    }


def test_all_product_consumers_resolve_the_exact_same_semantic_authority() -> None:
    terms = [term()]
    answers = [
        resolve_for_jarvis(terms, **kwargs()),
        resolve_for_insight(terms, **kwargs()),
        resolve_for_academy(terms, **kwargs()),
        resolve_for_help(terms, **kwargs()),
    ]
    assert {answer.concept_id for answer in answers} == {"tenant-a-nsfr-v3"}
    assert {answer.version for answer in answers} == {3}
    assert {answer.formula for answer in answers} == {"PFR + Refund + Compensation"}
    assert all(answer.authoritative is True for answer in answers)


@pytest.mark.parametrize(
    "resolver",
    [resolve_for_jarvis, resolve_for_insight, resolve_for_academy, resolve_for_help],
)
def test_all_product_consumers_fail_closed_when_company_semantics_are_missing(resolver) -> None:
    missing = {**kwargs(), "tenant_id": "tenant-b"}
    with pytest.raises(SemanticAuthorityUnavailable, match="no approved effective semantic definition"):
        resolver([term()], **missing)
