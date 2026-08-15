from __future__ import annotations

from datetime import datetime

from .models import GlossaryAnswer, GlossaryTerm
from .resolver import GlossaryResolutionError, resolve_term


class JarvisGlossaryAnswerUnavailable(LookupError):
    """Raised when Jarvis has no approved company definition to cite."""


def answer_business_term(
    terms: list[GlossaryTerm],
    *,
    tenant_id: str,
    query: str,
    locale: str,
    country: str | None = None,
    region: str | None = None,
    business_unit: str | None = None,
    domain: str | None = None,
    at: datetime | None = None,
) -> GlossaryAnswer:
    """Resolve terminology strictly from approved tenant semantics.

    This function intentionally has no web/general-knowledge fallback. A missing
    company term must surface as unavailable rather than allowing Jarvis to invent
    a company-specific definition or formula.
    """

    try:
        return resolve_term(
            terms,
            tenant_id=tenant_id,
            query=query,
            locale=locale,
            country=country,
            region=region,
            business_unit=business_unit,
            domain=domain,
            at=at,
        )
    except GlossaryResolutionError as exc:
        raise JarvisGlossaryAnswerUnavailable(
            "no approved effective company definition is available"
        ) from exc
