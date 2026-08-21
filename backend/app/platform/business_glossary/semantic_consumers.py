from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from .models import GlossaryAmbiguityCandidate, GlossaryAnswer, GlossaryTerm
from .resolver import GlossaryResolutionError, resolve_term


class SemanticConsumer(StrEnum):
    JARVIS = "jarvis"
    INSIGHT = "insight"
    ACADEMY = "academy"
    HELP = "help"
    KPI_CATALOG = "kpi_catalog"


class SemanticAuthorityUnavailable(LookupError):
    def __init__(self, message: str, *, candidates: list[GlossaryAmbiguityCandidate] | None = None) -> None:
        super().__init__(message)
        self.candidates = list(candidates or [])


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
        if exc.candidates:
            raise SemanticAuthorityUnavailable(
                f"semantic scope context is required for {consumer.value}",
                candidates=exc.candidates,
            ) from exc
        raise SemanticAuthorityUnavailable(
            f"no approved effective semantic definition is available for {consumer.value}"
        ) from exc
    if not answer.authoritative:
        raise SemanticAuthorityUnavailable("semantic authority returned non-authoritative data")
    return answer


def resolve_for_jarvis(terms: list[GlossaryTerm], **kwargs) -> GlossaryAnswer:
    return resolve_for_consumer(terms, consumer=SemanticConsumer.JARVIS, **kwargs)


def resolve_for_insight(terms: list[GlossaryTerm], **kwargs) -> GlossaryAnswer:
    return resolve_for_consumer(terms, consumer=SemanticConsumer.INSIGHT, **kwargs)


def resolve_for_academy(terms: list[GlossaryTerm], **kwargs) -> GlossaryAnswer:
    return resolve_for_consumer(terms, consumer=SemanticConsumer.ACADEMY, **kwargs)


def resolve_for_help(terms: list[GlossaryTerm], **kwargs) -> GlossaryAnswer:
    return resolve_for_consumer(terms, consumer=SemanticConsumer.HELP, **kwargs)


def resolve_for_kpi_catalog(terms: list[GlossaryTerm], **kwargs) -> GlossaryAnswer:
    """Resolve a KPI only when formula and source bindings come from one effective version."""
    answer = resolve_for_consumer(terms, consumer=SemanticConsumer.KPI_CATALOG, **kwargs)
    if not answer.formula or not answer.formula.strip():
        raise SemanticAuthorityUnavailable("effective KPI definition has no governed formula")
    if not answer.data_source_refs:
        raise SemanticAuthorityUnavailable("effective KPI definition has no governed data source binding")
    if any(not ref.strip() for ref in answer.data_source_refs):
        raise SemanticAuthorityUnavailable("effective KPI definition has an invalid data source binding")
    return answer
