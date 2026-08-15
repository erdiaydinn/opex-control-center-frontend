from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.jarvis import (
    JarvisGlossaryAnswerUnavailable,
    answer_business_term,
)
from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText
from app.platform.business_glossary.resolver import GlossaryResolutionError, resolve_term


def term(tenant: str, definition: str, *, country=None, version=1):
    return GlossaryTerm(
        concept_id=f"{tenant}-nsfr-{version}",
        canonical_key="nsfr",
        scope=GlossaryScope(tenant_id=tenant, country=country, domain="operations"),
        status=GlossaryStatus.EFFECTIVE,
        version=version,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        display_name=LocalizedText(values={"tr": "NSFR", "en": "NSFR"}),
        short_definition=LocalizedText(values={"tr": definition, "en": definition}),
        aliases=["service failure"],
        owner="ops-excellence",
    )


def test_resolver_never_crosses_tenant_boundary():
    terms = [term("tenant-a", "A definition"), term("tenant-b", "B definition")]
    answer = resolve_term(terms, tenant_id="tenant-a", query="NSFR", locale="tr", domain="operations")
    assert answer.definition == "A definition"


def test_country_override_wins_over_tenant_default():
    terms = [term("tenant-a", "Global company definition"), term("tenant-a", "TR definition", country="TR", version=2)]
    answer = resolve_term(terms, tenant_id="tenant-a", country="TR", query="service failure", locale="tr", domain="operations")
    assert answer.definition == "TR definition"
    assert answer.version == 2


def test_equally_authoritative_definitions_fail_closed_instead_of_using_input_order():
    country_term = term("tenant-a", "Country scoped", country="TR", version=2)
    business_unit_term = term("tenant-a", "Business unit scoped", version=2).model_copy(
        update={
            "concept_id": "tenant-a-nsfr-business-unit",
            "scope": GlossaryScope(tenant_id="tenant-a", business_unit="darkstore", domain="operations"),
        }
    )
    with pytest.raises(GlossaryResolutionError, match="ambiguous equally authoritative"):
        resolve_term(
            [country_term, business_unit_term],
            tenant_id="tenant-a",
            country="TR",
            business_unit="darkstore",
            domain="operations",
            query="NSFR",
            locale="tr",
        )


def test_undefined_company_term_fails_closed_instead_of_inventing_definition():
    with pytest.raises(GlossaryResolutionError, match="no approved effective tenant glossary definition"):
        resolve_term([term("tenant-a", "A definition")], tenant_id="tenant-b", query="NSFR", locale="tr", domain="operations")


def test_jarvis_uses_effective_tenant_definition():
    answer = answer_business_term(
        [term("tenant-a", "Company-approved NSFR meaning")],
        tenant_id="tenant-a",
        query="NSFR",
        locale="tr",
        domain="operations",
    )
    assert answer.authoritative is True
    assert answer.definition == "Company-approved NSFR meaning"


def test_jarvis_has_no_general_knowledge_fallback_for_company_term():
    with pytest.raises(JarvisGlossaryAnswerUnavailable, match="no approved effective company definition"):
        answer_business_term(
            [term("tenant-a", "Company A definition")],
            tenant_id="tenant-b",
            query="NSFR",
            locale="tr",
            domain="operations",
        )


def test_glossary_rejects_locale_outside_platform_contract():
    with pytest.raises(ValueError, match="unsupported glossary locales"):
        LocalizedText(values={"xx": "not supported"})


def test_jarvis_rejects_unknown_requested_locale():
    with pytest.raises(ValueError, match="unsupported requested glossary locale"):
        answer_business_term(
            [term("tenant-a", "Company A definition")],
            tenant_id="tenant-a",
            query="NSFR",
            locale="xx",
            domain="operations",
        )
