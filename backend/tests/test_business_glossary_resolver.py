from datetime import datetime, timezone

import pytest

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


def test_undefined_company_term_fails_closed_instead_of_inventing_definition():
    with pytest.raises(GlossaryResolutionError, match="no approved effective tenant glossary definition"):
        resolve_term([term("tenant-a", "A definition")], tenant_id="tenant-b", query="NSFR", locale="tr", domain="operations")
