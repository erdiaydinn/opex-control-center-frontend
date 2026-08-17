from __future__ import annotations

from pydantic import BaseModel, Field

from .jarvis import answer_business_term
from .models import GlossaryAnswer, GlossaryTerm


class GlossaryAuthorityContext(BaseModel):
    """Server-authoritative semantic scope derived from authenticated principal."""

    tenant_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    country: str | None = None
    region: str | None = None
    business_unit: str | None = None
    allowed_domains: frozenset[str] = Field(default_factory=frozenset)


class GlossaryAuthorizationError(PermissionError):
    pass


def answer_business_term_authorized(
    terms: list[GlossaryTerm],
    *,
    authority: GlossaryAuthorityContext,
    query: str,
    locale: str,
    domain: str | None = None,
) -> GlossaryAnswer:
    """Resolve Jarvis glossary answer without accepting caller-selected tenant authority."""
    if domain and authority.allowed_domains and domain not in authority.allowed_domains:
        raise GlossaryAuthorizationError("requested business domain is outside principal authority")
    return answer_business_term(
        terms,
        tenant_id=authority.tenant_id,
        query=query,
        locale=locale,
        country=authority.country,
        region=authority.region,
        business_unit=authority.business_unit,
        domain=domain,
    )
