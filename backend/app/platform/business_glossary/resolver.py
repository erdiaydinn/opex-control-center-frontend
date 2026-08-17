from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    GlossaryAmbiguityCandidate,
    GlossaryAnswer,
    GlossaryStatus,
    GlossaryTerm,
    locale_value,
)


class GlossaryResolutionError(LookupError):
    def __init__(self, message: str, *, candidates: list[GlossaryAmbiguityCandidate] | None = None) -> None:
        super().__init__(message)
        self.candidates = list(candidates or [])


def _scope_matches(term: GlossaryTerm, tenant_id: str, country: str | None, region: str | None, business_unit: str | None, domain: str | None) -> bool:
    scope = term.scope
    if scope.tenant_id != tenant_id:
        return False
    dimensions = ((scope.country, country), (scope.region, region), (scope.business_unit, business_unit), (scope.domain, domain))
    return all(expected is None or expected == actual for expected, actual in dimensions)


def _scope_compatible_for_discovery(term: GlossaryTerm, tenant_id: str, country: str | None, region: str | None, business_unit: str | None, domain: str | None) -> bool:
    scope = term.scope
    if scope.tenant_id != tenant_id:
        return False
    dimensions = ((scope.country, country), (scope.region, region), (scope.business_unit, business_unit), (scope.domain, domain))
    return all(actual is None or expected is None or expected == actual for expected, actual in dimensions)


def _specificity(term: GlossaryTerm) -> int:
    scope = term.scope
    return sum(value is not None for value in (scope.country, scope.region, scope.business_unit, scope.domain))


def _authority_rank(term: GlossaryTerm) -> tuple[int, int]:
    return (_specificity(term), term.version)


def _is_effective_at(term: GlossaryTerm, at: datetime) -> bool:
    if term.status != GlossaryStatus.EFFECTIVE:
        return False
    if term.effective_from and term.effective_from > at:
        return False
    if term.effective_to and term.effective_to <= at:
        return False
    return True


def _query_matches(term: GlossaryTerm, normalized: str) -> bool:
    names = {
        term.canonical_key.casefold(),
        *(alias.casefold() for alias in term.aliases),
        *(binding.value.casefold() for binding in term.alias_bindings),
    }
    names.update(value.casefold() for value in term.display_name.values.values())
    return normalized in names


def _candidate_contexts(terms: list[GlossaryTerm], locale: str) -> list[GlossaryAmbiguityCandidate]:
    ordered = sorted(terms, key=lambda item: (_authority_rank(item), item.concept_id), reverse=True)
    return [
        GlossaryAmbiguityCandidate(
            concept_id=item.concept_id,
            canonical_key=item.canonical_key,
            display_name=locale_value(item.display_name, locale),
            scope=item.scope,
            version=item.version,
        )
        for item in ordered
    ]


def resolve_term(
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
    now = at or datetime.now(timezone.utc)
    normalized = query.strip().casefold()
    active_matches = [term for term in terms if _is_effective_at(term, now) and _query_matches(term, normalized)]
    candidates = [
        term
        for term in active_matches
        if _scope_matches(term, tenant_id, country, region, business_unit, domain)
    ]

    if not candidates:
        discoverable = [
            term
            for term in active_matches
            if _scope_compatible_for_discovery(term, tenant_id, country, region, business_unit, domain)
        ]
        if discoverable:
            raise GlossaryResolutionError(
                "semantic scope context is required to resolve this tenant glossary term",
                candidates=_candidate_contexts(discoverable, locale),
            )
        raise GlossaryResolutionError("no approved effective tenant glossary definition")

    candidates.sort(key=_authority_rank, reverse=True)
    selected = candidates[0]
    selected_rank = _authority_rank(selected)
    equally_authoritative = [item for item in candidates if _authority_rank(item) == selected_rank]
    if len(equally_authoritative) > 1:
        identities = {(item.concept_id, item.canonical_key) for item in equally_authoritative}
        if len(identities) > 1:
            raise GlossaryResolutionError(
                "ambiguous equally authoritative tenant glossary definitions",
                candidates=_candidate_contexts(equally_authoritative, locale),
            )

    return GlossaryAnswer(
        concept_id=selected.concept_id,
        canonical_key=selected.canonical_key,
        locale=locale,
        display_name=locale_value(selected.display_name, locale),
        definition=locale_value(selected.short_definition, locale),
        formula=selected.formula,
        unit=selected.unit,
        data_source_refs=list(selected.data_source_refs),
        alias_bindings=list(selected.alias_bindings),
        concept_relations=list(selected.concept_relations),
        scope=selected.scope,
        version=selected.version,
        authoritative=True,
    )
