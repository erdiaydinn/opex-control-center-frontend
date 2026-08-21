from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .models import GlossaryStatus, GlossaryTerm


class GlossaryGovernanceError(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[GlossaryStatus, frozenset[GlossaryStatus]] = {
    GlossaryStatus.DRAFT: frozenset({GlossaryStatus.REVIEW}),
    GlossaryStatus.REVIEW: frozenset({GlossaryStatus.DRAFT, GlossaryStatus.APPROVED}),
    GlossaryStatus.APPROVED: frozenset({GlossaryStatus.EFFECTIVE, GlossaryStatus.DRAFT}),
    GlossaryStatus.EFFECTIVE: frozenset({GlossaryStatus.SUPERSEDED}),
    GlossaryStatus.SUPERSEDED: frozenset(),
}


def transition_term(
    term: GlossaryTerm,
    *,
    to_status: GlossaryStatus,
    actor_id: str,
    at: datetime,
) -> GlossaryTerm:
    """Return a new governed term state without mutating historical versions."""
    if not actor_id.strip():
        raise GlossaryGovernanceError("actor_id is required for glossary governance")
    if to_status not in _ALLOWED_TRANSITIONS[term.status]:
        raise GlossaryGovernanceError(f"invalid glossary transition: {term.status.value} -> {to_status.value}")

    payload = term.model_dump()
    payload["status"] = to_status
    metadata = dict(term.metadata)
    metadata["last_transition_actor"] = actor_id
    metadata["last_transition_at"] = at.isoformat()
    payload["metadata"] = metadata

    if to_status is GlossaryStatus.EFFECTIVE:
        payload["effective_from"] = at
    if to_status is GlossaryStatus.SUPERSEDED:
        payload["effective_to"] = at

    return GlossaryTerm.model_validate(payload)


def create_next_version(term: GlossaryTerm, *, actor_id: str) -> GlossaryTerm:
    if term.status not in {GlossaryStatus.EFFECTIVE, GlossaryStatus.SUPERSEDED}:
        raise GlossaryGovernanceError("new glossary versions require an effective/superseded source")
    if not actor_id.strip():
        raise GlossaryGovernanceError("actor_id is required for glossary versioning")
    payload = term.model_dump()
    payload.update(
        status=GlossaryStatus.DRAFT,
        version=term.version + 1,
        effective_from=None,
        effective_to=None,
    )
    metadata = dict(term.metadata)
    metadata["derived_from_version"] = term.version
    metadata["version_created_by"] = actor_id
    payload["metadata"] = metadata
    return GlossaryTerm.model_validate(payload)
