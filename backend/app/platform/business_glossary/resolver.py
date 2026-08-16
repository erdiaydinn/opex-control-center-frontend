from __future__ import annotations

from datetime import datetime, timezone

from .models import GlossaryAnswer, GlossaryStatus, GlossaryTerm, locale_value


class GlossaryResolutionError(LookupError):
    pass


def _scope_matches(term: GlossaryTerm, tenant_id: str, country: str | None, region: str | None, business_unit: str | None, domain: str | None) -> bool:
    scope = term.scope
    if scope.tenant_id != tenant_id:
        return False
    dimensions = ((scope.country, country), (scope.region, region), (scope.business_unit, business_unit), (scope.domain, domain))
    return all(expected is None or expected == actual for expected, actual in dimensions)


def _specificity(term: GlossaryTerm) -> int:
    scope = term.scope
    return sum(value is not None for value in (scope.country, scope.region, scope.business_unit, scope.domain))


def _authority_rank(term: GlossaryTerm) -> tuple[int, int]:
    return (_specificity(term), term.version)


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
    candidates: list[GlossaryTerm] = []
    for term in terms:
        if term.status != GlossaryStatus.EFFECTIVE:
            continue
        if not _scope_matches(term, tenant_id, country, region, business_unit, domain):
            continue
        if term.effective_from and term.effective_from > now:
            continue
        if term.effective_to and term.effective_to <= now:
            continue
        names = {term.canonical_key.casefold(), *(alias.casefold() for alias in term.aliases)}
        names.update(value.casefold() for value in term.display_name.values.values())
        if normalized in names:
            candidates.append(term)

    if not candidates:
        raise GlossaryResolutionError("no approved effective tenant glossary definition")

    candidates.sort(key=_authority_rank, reverse=True)
    selected = candidates[0]
    selected_rank = _authority_rank(selected)
    equally_authoritative = [item for item in candidates if _authority_rank(item) == selected_rank]
    if len(equally_authoritative) > 1:
        identities = {(item.concept_id, item.canonical_key) for item in equally_authoritative}
        if len(identities) > 1:
            raise GlossaryResolutionError("ambiguous equally authoritative tenant glossary definitions")

    return GlossaryAnswer(
        concept_id=selected.concept_id,
        canonical_key=selected.canonical_key,
        locale=locale,
        display_name=locale_value(selected.display_name, locale),
        definition=locale_value(selected.short_definition, locale),
        formula=selected.formula,
        unit=selected.unit,
        scope=selected.scope,
        version=selected.version,
        authoritative=True,
    )
