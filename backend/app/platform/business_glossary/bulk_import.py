from __future__ import annotations

import csv
import hashlib
import io
import json
from enum import StrEnum
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .governance import create_next_version
from .models import (
    GlossaryAliasBinding,
    GlossaryConceptRelation,
    GlossaryScope,
    GlossaryStatus,
    GlossaryTerm,
    LocalizedText,
)


class GlossaryBulkImportError(ValueError):
    pass


class GlossaryImportAction(StrEnum):
    NO_CHANGE = "no_change"
    NEW_DRAFT = "new_draft"
    NEW_VERSION_DRAFT = "new_version_draft"


class GlossaryImportRow(BaseModel):
    tenant_id: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    canonical_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    country: str | None = None
    region: str | None = None
    business_unit: str | None = None
    domain: str | None = None
    display_name: dict[str, str]
    short_definition: dict[str, str]
    detailed_definition: dict[str, str] | None = None
    aliases: list[str] = Field(default_factory=list)
    alias_bindings: list[GlossaryAliasBinding] = Field(default_factory=list)
    formula: str | None = None
    unit: str | None = None
    data_source_refs: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    concept_relations: list[GlossaryConceptRelation] = Field(default_factory=list)
    owner: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GlossaryFieldDiff(BaseModel):
    field: str
    before: Any = None
    after: Any = None


class GlossaryImportEntry(BaseModel):
    concept_id: str
    canonical_key: str
    action: GlossaryImportAction
    source_version: int | None = None
    proposed_version: int | None = None
    diff: list[GlossaryFieldDiff] = Field(default_factory=list)
    proposed_term: GlossaryTerm | None = None


class GlossaryImportPlan(BaseModel):
    tenant_id: str
    fingerprint: str
    entries: list[GlossaryImportEntry]
    review_required: bool = True
    automatic_effective_permitted: bool = False


_SEMANTIC_FIELDS = (
    "canonical_key",
    "scope",
    "display_name",
    "short_definition",
    "detailed_definition",
    "aliases",
    "alias_bindings",
    "formula",
    "unit",
    "data_source_refs",
    "related_concepts",
    "concept_relations",
    "owner",
)
_JSON_COLUMNS = {
    "display_name",
    "short_definition",
    "detailed_definition",
    "aliases",
    "alias_bindings",
    "data_source_refs",
    "related_concepts",
    "concept_relations",
    "metadata",
}


def rows_from_api(payload: Iterable[dict[str, Any]]) -> list[GlossaryImportRow]:
    return [GlossaryImportRow.model_validate(item) for item in payload]


def rows_from_csv(text: str) -> list[GlossaryImportRow]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise GlossaryBulkImportError("CSV import requires a header row")
    rows: list[GlossaryImportRow] = []
    for raw in reader:
        payload: dict[str, Any] = {}
        for key, value in raw.items():
            if key is None or value is None:
                continue
            value = value.strip()
            if key in _JSON_COLUMNS:
                if value == "":
                    if key in {"display_name", "short_definition"}:
                        payload[key] = {}
                    elif key in {"detailed_definition", "metadata"}:
                        payload[key] = None if key == "detailed_definition" else {}
                    else:
                        payload[key] = []
                else:
                    try:
                        payload[key] = json.loads(value)
                    except json.JSONDecodeError as exc:
                        raise GlossaryBulkImportError(f"invalid JSON in CSV column {key}") from exc
            else:
                payload[key] = value or None
        rows.append(GlossaryImportRow.model_validate(payload))
    return rows


def _row_identity(row: GlossaryImportRow) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    return (row.tenant_id, row.concept_id, row.country, row.region, row.business_unit, row.domain)


def _identity_sort_key(identity: tuple[str, str, str | None, str | None, str | None, str | None]) -> tuple[str, ...]:
    return tuple(value or "" for value in identity)


def _term_identity(term: GlossaryTerm) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    scope = term.scope
    return (scope.tenant_id, term.concept_id, scope.country, scope.region, scope.business_unit, scope.domain)


def _term_from_row(row: GlossaryImportRow, *, version: int, metadata: dict[str, Any] | None = None) -> GlossaryTerm:
    return GlossaryTerm(
        concept_id=row.concept_id,
        canonical_key=row.canonical_key,
        scope=GlossaryScope(
            tenant_id=row.tenant_id,
            country=row.country,
            region=row.region,
            business_unit=row.business_unit,
            domain=row.domain,
        ),
        status=GlossaryStatus.DRAFT,
        version=version,
        display_name=LocalizedText(values=row.display_name),
        short_definition=LocalizedText(values=row.short_definition),
        detailed_definition=LocalizedText(values=row.detailed_definition) if row.detailed_definition else None,
        aliases=list(row.aliases),
        alias_bindings=list(row.alias_bindings),
        formula=row.formula,
        unit=row.unit,
        data_source_refs=list(row.data_source_refs),
        related_concepts=list(row.related_concepts),
        concept_relations=list(row.concept_relations),
        owner=row.owner,
        metadata=dict(metadata if metadata is not None else row.metadata),
    )


def _semantic_payload(term: GlossaryTerm) -> dict[str, Any]:
    payload = term.model_dump(mode="json")
    return {field: payload[field] for field in _SEMANTIC_FIELDS}


def _diff(before: GlossaryTerm, after: GlossaryTerm) -> list[GlossaryFieldDiff]:
    left = _semantic_payload(before)
    right = _semantic_payload(after)
    return [
        GlossaryFieldDiff(field=field, before=left[field], after=right[field])
        for field in _SEMANTIC_FIELDS
        if left[field] != right[field]
    ]


def _fingerprint(tenant_id: str, rows: list[GlossaryImportRow]) -> str:
    ordered = sorted(rows, key=lambda row: _identity_sort_key(_row_identity(row)))
    canonical = [row.model_dump(mode="json", exclude_none=False) for row in ordered]
    raw = json.dumps({"tenant_id": tenant_id, "rows": canonical}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan_bulk_import(
    *,
    tenant_id: str,
    rows: list[GlossaryImportRow],
    current_terms: list[GlossaryTerm],
    actor_id: str,
) -> GlossaryImportPlan:
    if not tenant_id.strip() or not actor_id.strip():
        raise GlossaryBulkImportError("tenant_id and actor_id are required")
    if any(row.tenant_id != tenant_id for row in rows):
        raise GlossaryBulkImportError("cross-tenant glossary import row rejected")

    identities = [_row_identity(row) for row in rows]
    if len(set(identities)) != len(identities):
        raise GlossaryBulkImportError("duplicate glossary import identity")

    current_by_identity: dict[tuple[str, str, str | None, str | None, str | None, str | None], GlossaryTerm] = {}
    for term in current_terms:
        if term.scope.tenant_id != tenant_id or term.status is not GlossaryStatus.EFFECTIVE:
            continue
        identity = _term_identity(term)
        if identity in current_by_identity:
            raise GlossaryBulkImportError("multiple effective glossary versions for one semantic identity")
        current_by_identity[identity] = term

    entries: list[GlossaryImportEntry] = []
    for row in sorted(rows, key=lambda item: _identity_sort_key(_row_identity(item))):
        current = current_by_identity.get(_row_identity(row))
        if current is None:
            proposed = _term_from_row(row, version=1)
            entries.append(
                GlossaryImportEntry(
                    concept_id=row.concept_id,
                    canonical_key=row.canonical_key,
                    action=GlossaryImportAction.NEW_DRAFT,
                    proposed_version=1,
                    diff=[GlossaryFieldDiff(field=field, before=None, after=value) for field, value in _semantic_payload(proposed).items()],
                    proposed_term=proposed,
                )
            )
            continue

        candidate = _term_from_row(row, version=current.version + 1)
        changes = _diff(current, candidate)
        if not changes:
            entries.append(
                GlossaryImportEntry(
                    concept_id=row.concept_id,
                    canonical_key=row.canonical_key,
                    action=GlossaryImportAction.NO_CHANGE,
                    source_version=current.version,
                )
            )
            continue

        next_version = create_next_version(current, actor_id=actor_id)
        proposed_payload = candidate.model_dump()
        proposed_payload["version"] = next_version.version
        proposed_metadata = dict(row.metadata)
        proposed_metadata.update(next_version.metadata)
        proposed_payload["metadata"] = proposed_metadata
        proposed = GlossaryTerm.model_validate(proposed_payload)
        entries.append(
            GlossaryImportEntry(
                concept_id=row.concept_id,
                canonical_key=row.canonical_key,
                action=GlossaryImportAction.NEW_VERSION_DRAFT,
                source_version=current.version,
                proposed_version=proposed.version,
                diff=changes,
                proposed_term=proposed,
            )
        )

    return GlossaryImportPlan(
        tenant_id=tenant_id,
        fingerprint=_fingerprint(tenant_id, rows),
        entries=entries,
    )
