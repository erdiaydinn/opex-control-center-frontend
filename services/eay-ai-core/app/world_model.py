"""Temporal company world-state model for Jarvis.

The world model composes already-governed observations; it is not a new source
of truth.  Every assertion is tenant-bound, time-bound and provenance-bound.
Lower-authority analytic inference may enrich direct truth but may never
silently override it.  Equal-authority contradictions are exposed as blocked
fields rather than guessed away.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

WORLD_MODEL_CONTRACT = "eay-company-world-model-v1"


class EntityKind(str, Enum):
    COMPANY = "company"
    WAREHOUSE = "warehouse"
    STORE = "store"
    EMPLOYEE = "employee"
    SKU = "sku"
    PRODUCT = "product"
    SUPPLIER = "supplier"
    ORDER = "order"
    CUSTOMER_COHORT = "customer_cohort"
    ASSET = "asset"
    SYSTEM = "system"
    POLICY = "policy"
    LEGAL_INSTRUMENT = "legal_instrument"
    EXTERNAL_EVENT = "external_event"
    KPI = "kpi"
    BUDGET = "budget"
    PROJECT = "project"


class TruthClass(str, Enum):
    GOVERNED_OPERATIONAL = "governed_operational"
    VERIFIED_COMPANY = "verified_company"
    VERIFIED_LEGAL = "verified_legal"
    VERIFIED_EXTERNAL = "verified_external"
    ANALYTIC_INFERENCE = "analytic_inference"


_TRUTH_PRIORITY = {
    TruthClass.GOVERNED_OPERATIONAL: 100,
    TruthClass.VERIFIED_COMPANY: 90,
    TruthClass.VERIFIED_LEGAL: 90,
    TruthClass.VERIFIED_EXTERNAL: 70,
    TruthClass.ANALYTIC_INFERENCE: 40,
}


class WorldEntity(BaseModel):
    entity_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    kind: EntityKind
    display_name: str = Field(min_length=1)
    external_refs: tuple[str, ...] = ()


class WorldRelation(BaseModel):
    relation_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_entity_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    valid_from: datetime
    valid_to: datetime | None = None
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def temporal_contract(self) -> "WorldRelation":
        _require_aware(self.valid_from, "world_relation_valid_from_requires_timezone")
        if self.valid_to is not None:
            _require_aware(self.valid_to, "world_relation_valid_to_requires_timezone")
            if self.valid_to <= self.valid_from:
                raise ValueError("world_relation_valid_to_must_follow_valid_from")
        return self


class WorldAssertion(BaseModel):
    assertion_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    value: Any
    truth_class: TruthClass
    valid_from: datetime
    valid_to: datetime | None = None
    observed_at: datetime
    source_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def temporal_and_truth_contract(self) -> "WorldAssertion":
        _require_aware(self.valid_from, "world_assertion_valid_from_requires_timezone")
        _require_aware(self.observed_at, "world_assertion_observed_at_requires_timezone")
        if self.valid_to is not None:
            _require_aware(self.valid_to, "world_assertion_valid_to_requires_timezone")
            if self.valid_to <= self.valid_from:
                raise ValueError("world_assertion_valid_to_must_follow_valid_from")
        if self.observed_at < self.valid_from and self.truth_class is TruthClass.GOVERNED_OPERATIONAL:
            raise ValueError("operational_observation_cannot_predate_valid_state")
        return self


class ResolvedField(BaseModel):
    entity_id: str
    field_name: str
    value: Any
    truth_class: TruthClass
    confidence: float
    assertion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]


class WorldContradiction(BaseModel):
    entity_id: str
    field_name: str
    assertion_ids: tuple[str, ...]
    reason: str


class WorldSnapshot(BaseModel):
    contract: str = WORLD_MODEL_CONTRACT
    tenant_id: str
    as_of: datetime
    entities: tuple[WorldEntity, ...]
    fields: tuple[ResolvedField, ...]
    relations: tuple[WorldRelation, ...]
    contradictions: tuple[WorldContradiction, ...]
    blocked_field_keys: tuple[str, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def snapshot_time_is_aware(self) -> "WorldSnapshot":
        _require_aware(self.as_of, "world_snapshot_as_of_requires_timezone")
        return self


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _active(valid_from: datetime, valid_to: datetime | None, as_of: datetime) -> bool:
    return valid_from <= as_of and (valid_to is None or as_of < valid_to)


def _canonical_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _snapshot_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_world_snapshot(
    *,
    tenant_id: str,
    as_of: datetime,
    entities: list[WorldEntity],
    assertions: list[WorldAssertion],
    relations: list[WorldRelation] | None = None,
) -> WorldSnapshot:
    _require_aware(as_of, "world_snapshot_as_of_requires_timezone")
    tenant_entities = tuple(sorted((e for e in entities if e.tenant_id == tenant_id), key=lambda e: e.entity_id))
    entity_ids = {entity.entity_id for entity in tenant_entities}

    relevant = [
        assertion
        for assertion in assertions
        if assertion.tenant_id == tenant_id
        and assertion.entity_id in entity_ids
        and _active(assertion.valid_from, assertion.valid_to, as_of)
    ]

    grouped: dict[tuple[str, str], list[WorldAssertion]] = {}
    for assertion in relevant:
        grouped.setdefault((assertion.entity_id, assertion.field_name), []).append(assertion)

    fields: list[ResolvedField] = []
    contradictions: list[WorldContradiction] = []
    blocked: list[str] = []

    for (entity_id, field_name), candidates in sorted(grouped.items()):
        highest_priority = max(_TRUTH_PRIORITY[item.truth_class] for item in candidates)
        highest = [item for item in candidates if _TRUTH_PRIORITY[item.truth_class] == highest_priority]
        value_groups: dict[str, list[WorldAssertion]] = {}
        for item in highest:
            value_groups.setdefault(_canonical_value(item.value), []).append(item)

        field_key = f"{entity_id}:{field_name}"
        if len(value_groups) > 1:
            ids = tuple(sorted(item.assertion_id for item in highest))
            contradictions.append(
                WorldContradiction(
                    entity_id=entity_id,
                    field_name=field_name,
                    assertion_ids=ids,
                    reason="equal_authority_active_assertions_conflict",
                )
            )
            blocked.append(field_key)
            continue

        selected = sorted(
            highest,
            key=lambda item: (item.confidence, item.observed_at, item.assertion_id),
            reverse=True,
        )
        winner = selected[0]
        supporting = [item for item in highest if _canonical_value(item.value) == _canonical_value(winner.value)]
        fields.append(
            ResolvedField(
                entity_id=entity_id,
                field_name=field_name,
                value=winner.value,
                truth_class=winner.truth_class,
                confidence=max(item.confidence for item in supporting),
                assertion_ids=tuple(sorted(item.assertion_id for item in supporting)),
                evidence_refs=tuple(sorted({item.evidence_ref for item in supporting})),
            )
        )

    tenant_relations = tuple(
        sorted(
            (
                relation
                for relation in (relations or [])
                if relation.tenant_id == tenant_id
                and relation.source_entity_id in entity_ids
                and relation.target_entity_id in entity_ids
                and _active(relation.valid_from, relation.valid_to, as_of)
            ),
            key=lambda relation: relation.relation_id,
        )
    )

    fingerprint_payload = {
        "tenant_id": tenant_id,
        "as_of": as_of.isoformat(),
        "entities": [entity.model_dump(mode="json") for entity in tenant_entities],
        "fields": [field.model_dump(mode="json") for field in fields],
        "relations": [relation.model_dump(mode="json") for relation in tenant_relations],
        "contradictions": [item.model_dump(mode="json") for item in contradictions],
        "blocked": sorted(blocked),
    }

    return WorldSnapshot(
        tenant_id=tenant_id,
        as_of=as_of,
        entities=tenant_entities,
        fields=tuple(fields),
        relations=tenant_relations,
        contradictions=tuple(contradictions),
        blocked_field_keys=tuple(sorted(blocked)),
        fingerprint=_snapshot_fingerprint(fingerprint_payload),
    )
