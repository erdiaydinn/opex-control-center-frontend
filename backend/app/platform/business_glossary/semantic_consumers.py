from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from .models import GlossaryAnswer, GlossaryTerm
from .resolver import GlossaryResolutionError, resolve_term


class SemanticConsumer(StrEnum):
    JARVIS = "jarvis"
    INSIGHT = "insight"
    ACADEMY = "academy"
    HELP = "help"


class SemanticAuthorityUnavailable(LookupError):
    pass


def resolve_for_consumer(
    terms: list[GlossaryTerm],
    *,
    consumer: SemanticConsumer,
    tenant_id: str,
    query: str,
    locale: str,
    country: str | None = None,
    region: str | None = None,
    business_unit: str | None = None,
    domain: str | None = None,
    at: datetime | None = None,
) -> GlossaryAnswer:
    """Use the same approved semantic authority for every product consumer."""
    try:
        answer = resolve_term(
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
        raise SemanticAuthorityUnavailable(
            f"no approved effective semantic definition is available for {consumer.value}"
        ) from exc
    if not answer.authoritative:
        raise SemanticAuthorityUnavailable("semantic authority returned non-authoritative data")
    return answer
