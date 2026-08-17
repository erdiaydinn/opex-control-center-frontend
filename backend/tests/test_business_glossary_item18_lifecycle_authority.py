from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.jarvis import JarvisGlossaryAnswerUnavailable, answer_business_term
from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText

AT = datetime(2026, 8, 17, 11, 30, tzinfo=timezone.utc)
EFFECTIVE_FROM = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _term(status: GlossaryStatus, version: int, definition: str) -> GlossaryTerm:
    kwargs = {"effective_from": EFFECTIVE_FROM} if status is GlossaryStatus.EFFECTIVE else {}
    return GlossaryTerm(
        concept_id="tenant-a-nsfr",
        canonical_key="nsfr",
        scope=GlossaryScope(tenant_id="tenant-a", business_unit="Market", domain="operations"),
        status=status,
        version=version,
        display_name=LocalizedText(values={"tr": "NSFR", "en": "NSFR"}),
        short_definition=LocalizedText(values={"tr": definition, "en": definition}),
        aliases=["NSFR"],
        owner="semantic-governance",
        **kwargs,
    )


def test_jarvis_never_uses_draft_as_authoritative_definition() -> None:
    with pytest.raises(JarvisGlossaryAnswerUnavailable, match="no approved effective"):
        answer_business_term(
            [_term(GlossaryStatus.DRAFT, 2, "unreviewed draft")],
            tenant_id="tenant-a",
            query="NSFR",
            locale="en",
            business_unit="Market",
            domain="operations",
            at=AT,
        )


def test_newer_draft_cannot_override_current_effective_version_for_jarvis() -> None:
    answer = answer_business_term(
        [
            _term(GlossaryStatus.EFFECTIVE, 1, "current governed definition"),
            _term(GlossaryStatus.DRAFT, 2, "newer but unreviewed definition"),
        ],
        tenant_id="tenant-a",
        query="NSFR",
        locale="en",
        business_unit="Market",
        domain="operations",
        at=AT,
    )
    assert answer.version == 1
    assert answer.definition == "current governed definition"
    assert answer.authoritative is True
