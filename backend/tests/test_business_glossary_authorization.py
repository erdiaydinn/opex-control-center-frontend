from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.authorization import (
    GlossaryAuthorityContext,
    GlossaryAuthorizationError,
    answer_business_term_authorized,
)
from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText


def term(tenant: str, definition: str, domain="operations"):
    return GlossaryTerm(
        concept_id=f"{tenant}-backlog",
        canonical_key="backlog",
        scope=GlossaryScope(tenant_id=tenant, domain=domain),
        status=GlossaryStatus.EFFECTIVE,
        version=1,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        display_name=LocalizedText(values={"tr": "Backlog", "en": "Backlog"}),
        short_definition=LocalizedText(values={"tr": definition, "en": definition}),
        owner="ops-excellence",
    )


def test_jarvis_semantic_lookup_uses_principal_tenant_not_caller_tenant_parameter():
    authority = GlossaryAuthorityContext(
        tenant_id="tenant-a",
        subject_id="user-1",
        allowed_domains=frozenset({"operations"}),
    )
    answer = answer_business_term_authorized(
        [term("tenant-a", "Tenant A backlog"), term("tenant-b", "Tenant B backlog")],
        authority=authority,
        query="backlog",
        locale="tr",
        domain="operations",
    )
    assert answer.definition == "Tenant A backlog"
    assert answer.scope.tenant_id == "tenant-a"


def test_domain_outside_principal_scope_is_rejected_before_lookup():
    authority = GlossaryAuthorityContext(
        tenant_id="tenant-a",
        subject_id="user-1",
        allowed_domains=frozenset({"operations"}),
    )
    with pytest.raises(GlossaryAuthorizationError, match="outside principal authority"):
        answer_business_term_authorized(
            [term("tenant-a", "Finance term", domain="finance")],
            authority=authority,
            query="backlog",
            locale="tr",
            domain="finance",
        )
