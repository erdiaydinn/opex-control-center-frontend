from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.governance import (
    GlossaryGovernanceError,
    create_next_version,
    transition_term,
)
from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)


def draft_term(status=GlossaryStatus.DRAFT, version=1):
    kwargs = {}
    if status is GlossaryStatus.EFFECTIVE:
        kwargs["effective_from"] = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return GlossaryTerm(
        concept_id="tenant-a-backlog",
        canonical_key="backlog",
        scope=GlossaryScope(tenant_id="tenant-a", domain="operations"),
        status=status,
        version=version,
        display_name=LocalizedText(values={"tr": "Backlog", "en": "Backlog"}),
        short_definition=LocalizedText(values={"tr": "Onaylı şirket tanımı", "en": "Approved company meaning"}),
        owner="operations-excellence",
        **kwargs,
    )


def test_draft_review_approved_effective_lifecycle_is_explicit():
    review = transition_term(draft_term(), to_status=GlossaryStatus.REVIEW, actor_id="owner-1", at=NOW)
    approved = transition_term(review, to_status=GlossaryStatus.APPROVED, actor_id="reviewer-1", at=NOW)
    effective = transition_term(approved, to_status=GlossaryStatus.EFFECTIVE, actor_id="publisher-1", at=NOW)
    assert effective.status is GlossaryStatus.EFFECTIVE
    assert effective.effective_from == NOW
    assert effective.metadata["last_transition_actor"] == "publisher-1"


def test_effective_term_cannot_be_silently_edited_back_to_draft():
    with pytest.raises(GlossaryGovernanceError, match="invalid glossary transition"):
        transition_term(draft_term(status=GlossaryStatus.EFFECTIVE), to_status=GlossaryStatus.DRAFT, actor_id="editor", at=NOW)


def test_new_version_is_draft_and_preserves_lineage():
    source = draft_term(status=GlossaryStatus.EFFECTIVE, version=4)
    next_version = create_next_version(source, actor_id="editor-1")
    assert next_version.version == 5
    assert next_version.status is GlossaryStatus.DRAFT
    assert next_version.effective_from is None
    assert next_version.metadata["derived_from_version"] == 4
