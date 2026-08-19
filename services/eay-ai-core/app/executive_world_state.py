"""Decision-relevant views over the canonical EAY Company World Model.

The canonical :mod:`world_model` remains the source of company state. A
WorldSnapshot intentionally contains resolved fields, active relations,
contradictions and blocked keys rather than raw assertions. This module derives
bounded executive views from exactly that contract; it does not reconstruct or
invent raw assertion history.

Freshness is supplied separately as reference-only observation metadata because
ResolvedField intentionally does not retain observation timestamps. Snapshot
deltas carry value fingerprints rather than raw before/after values.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .world_model import ResolvedField, WorldContradiction, WorldEntity, WorldRelation, WorldSnapshot

EXECUTIVE_WORLD_STATE_CONTRACT = "eay-executive-world-state-v1"


class WorldRequirementStatus(str, Enum):
    READY = "ready"
    MISSING = "missing"
    BLOCKED = "blocked"
    STALE = "stale"
    FRESHNESS_UNKNOWN = "freshness_unknown"


class WorldChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    EVIDENCE_REFRESHED = "evidence_refreshed"


class ExecutiveFieldRequirement(BaseModel):
    entity_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    maximum_observation_age_seconds: int | None = Field(default=None, ge=0, le=31_536_000)


class FieldFreshnessObservation(BaseModel):
    entity_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    observed_at: datetime
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def observation_time_is_aware(self) -> "FieldFreshnessObservation":
        _aware(self.observed_at, "field_freshness_observed_at_requires_timezone")
        return self


class ExecutiveFieldReadiness(BaseModel):
    entity_id: str
    field_name: str
    status: WorldRequirementStatus
    assertion_ids: tuple[str, ...] = ()
    truth_class: str | None = None
    evidence_refs: tuple[str, ...] = ()
    observed_at: datetime | None = None
    freshness_evidence_ref: str | None = None
    blocker: str | None = None


class ExecutiveWorldReadiness(BaseModel):
    contract: str = EXECUTIVE_WORLD_STATE_CONTRACT
    tenant_id: str
    world_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    as_of: datetime
    fields: tuple[ExecutiveFieldReadiness, ...]
    ready: bool
    blockers: tuple[str, ...] = ()
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def view_is_non_authoritative(self) -> "ExecutiveWorldReadiness":
        _aware(self.as_of, "executive_world_readiness_as_of_requires_timezone")
        if self.truth_authority_granted or self.execution_authority_granted:
            raise ValueError("executive_world_view_never_grants_authority")
        return self


class ExecutiveWorldSubgraph(BaseModel):
    contract: str = EXECUTIVE_WORLD_STATE_CONTRACT
    tenant_id: str
    parent_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    as_of: datetime
    entities: tuple[WorldEntity, ...]
    fields: tuple[ResolvedField, ...]
    relations: tuple[WorldRelation, ...]
    contradictions: tuple[WorldContradiction, ...]
    blocked_field_keys: tuple[str, ...]
    persistent_memory_authority: bool = False
    truth_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def subgraph_is_bounded_view(self) -> "ExecutiveWorldSubgraph":
        _aware(self.as_of, "executive_world_subgraph_as_of_requires_timezone")
        if self.persistent_memory_authority or self.truth_authority_granted:
            raise ValueError("executive_world_subgraph_never_becomes_truth_store")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("executive_world_subgraph_fingerprint_mismatch")
        return self


class WorldStateChange(BaseModel):
    field_key: str
    kind: WorldChangeKind
    before_value_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    after_value_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    before_assertion_ids: tuple[str, ...] = ()
    after_assertion_ids: tuple[str, ...] = ()
    before_evidence_refs: tuple[str, ...] = ()
    after_evidence_refs: tuple[str, ...] = ()


class WorldSnapshotDelta(BaseModel):
    contract: str = EXECUTIVE_WORLD_STATE_CONTRACT
    tenant_id: str
    before_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    before_as_of: datetime
    after_as_of: datetime
    changes: tuple[WorldStateChange, ...]
    changed_field_keys: tuple[str, ...]
    raw_values_retained: bool = False
    truth_authority_granted: bool = False

    @model_validator(mode="after")
    def delta_is_safe(self) -> "WorldSnapshotDelta":
        _aware(self.before_as_of, "world_delta_before_as_of_requires_timezone")
        _aware(self.after_as_of, "world_delta_after_as_of_requires_timezone")
        if self.after_as_of < self.before_as_of:
            raise ValueError("world_delta_after_predates_before")
        if self.raw_values_retained:
            raise ValueError("world_delta_raw_values_forbidden")
        if self.truth_authority_granted:
            raise ValueError("world_delta_never_grants_truth_authority")
        if len(self.changed_field_keys) != len(set(self.changed_field_keys)):
            raise ValueError("world_delta_changed_fields_must_be_unique")
        return self


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _value_fingerprint(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump(mode="json")
    data.pop("fingerprint", None)
    return data


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_decision_subgraph(
    *,
    snapshot: WorldSnapshot,
    seed_entity_ids: tuple[str, ...],
    relationship_hops: int = 1,
    field_allowlist: tuple[str, ...] = (),
) -> ExecutiveWorldSubgraph:
    """Derive a relation-aware, decision-relevant view from resolved state."""

    if not seed_entity_ids:
        raise ValueError("executive_world_subgraph_requires_seed_entity")
    if relationship_hops < 0 or relationship_hops > 4:
        raise ValueError("executive_world_subgraph_hops_out_of_range")
    entity_map = {item.entity_id: item for item in snapshot.entities}
    unknown = set(seed_entity_ids) - set(entity_map)
    if unknown:
        raise ValueError("executive_world_subgraph_unknown_seed_entity")

    selected = set(seed_entity_ids)
    frontier = set(seed_entity_ids)
    for _ in range(relationship_hops):
        next_frontier: set[str] = set()
        for relation in snapshot.relations:
            if relation.source_entity_id in frontier and relation.target_entity_id not in selected:
                next_frontier.add(relation.target_entity_id)
            if relation.target_entity_id in frontier and relation.source_entity_id not in selected:
                next_frontier.add(relation.source_entity_id)
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier

    allowed_fields = set(field_allowlist)
    entities = tuple(item for item in snapshot.entities if item.entity_id in selected)
    fields = tuple(
        item
        for item in snapshot.fields
        if item.entity_id in selected and (not allowed_fields or item.field_name in allowed_fields)
    )
    relations = tuple(
        item
        for item in snapshot.relations
        if item.source_entity_id in selected and item.target_entity_id in selected
    )
    contradictions = tuple(
        item for item in snapshot.contradictions if item.entity_id in selected
    )
    blocked = tuple(
        item
        for item in snapshot.blocked_field_keys
        if item.rsplit(":", 1)[0] in selected
    )
    draft = {
        "contract": EXECUTIVE_WORLD_STATE_CONTRACT,
        "tenant_id": snapshot.tenant_id,
        "parent_snapshot_fingerprint": snapshot.fingerprint,
        "as_of": snapshot.as_of.isoformat().replace("+00:00", "Z"),
        "entities": [item.model_dump(mode="json") for item in entities],
        "fields": [item.model_dump(mode="json") for item in fields],
        "relations": [item.model_dump(mode="json") for item in relations],
        "contradictions": [item.model_dump(mode="json") for item in contradictions],
        "blocked_field_keys": list(blocked),
        "persistent_memory_authority": False,
        "truth_authority_granted": False,
    }
    return ExecutiveWorldSubgraph.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def assess_executive_world_readiness(
    *,
    snapshot: WorldSnapshot,
    requirements: tuple[ExecutiveFieldRequirement, ...],
    freshness_observations: tuple[FieldFreshnessObservation, ...] = (),
) -> ExecutiveWorldReadiness:
    if not requirements:
        raise ValueError("executive_world_readiness_requires_fields")
    identities = [(item.entity_id, item.field_name) for item in requirements]
    if len(identities) != len(set(identities)):
        raise ValueError("executive_world_readiness_duplicate_requirement")

    fields_by_key = {(item.entity_id, item.field_name): item for item in snapshot.fields}
    freshness_map = {(item.entity_id, item.field_name): item for item in freshness_observations}
    if len(freshness_map) != len(freshness_observations):
        raise ValueError("executive_world_readiness_duplicate_freshness_observation")
    blocked = set(snapshot.blocked_field_keys)
    fields: list[ExecutiveFieldReadiness] = []
    blockers: list[str] = []

    for requirement in requirements:
        key = (requirement.entity_id, requirement.field_name)
        field_key = f"{requirement.entity_id}:{requirement.field_name}"
        resolved = fields_by_key.get(key)
        if field_key in blocked:
            blocker = f"world_field_blocked:{field_key}"
            blockers.append(blocker)
            fields.append(
                ExecutiveFieldReadiness(
                    entity_id=requirement.entity_id,
                    field_name=requirement.field_name,
                    status=WorldRequirementStatus.BLOCKED,
                    blocker=blocker,
                )
            )
            continue
        if resolved is None:
            blocker = f"world_field_missing:{field_key}"
            blockers.append(blocker)
            fields.append(
                ExecutiveFieldReadiness(
                    entity_id=requirement.entity_id,
                    field_name=requirement.field_name,
                    status=WorldRequirementStatus.MISSING,
                    blocker=blocker,
                )
            )
            continue

        freshness = freshness_map.get(key)
        if requirement.maximum_observation_age_seconds is None:
            status = WorldRequirementStatus.READY
            blocker = None
        elif freshness is None:
            status = WorldRequirementStatus.FRESHNESS_UNKNOWN
            blocker = f"world_field_freshness_unknown:{field_key}"
            blockers.append(blocker)
        else:
            age_seconds = (snapshot.as_of - freshness.observed_at).total_seconds()
            if age_seconds < 0:
                raise ValueError("world_field_freshness_observation_from_future")
            if age_seconds > requirement.maximum_observation_age_seconds:
                status = WorldRequirementStatus.STALE
                blocker = f"world_field_stale:{field_key}"
                blockers.append(blocker)
            else:
                status = WorldRequirementStatus.READY
                blocker = None

        fields.append(
            ExecutiveFieldReadiness(
                entity_id=requirement.entity_id,
                field_name=requirement.field_name,
                status=status,
                assertion_ids=resolved.assertion_ids,
                truth_class=resolved.truth_class.value,
                evidence_refs=resolved.evidence_refs,
                observed_at=freshness.observed_at if freshness is not None else None,
                freshness_evidence_ref=freshness.evidence_ref if freshness is not None else None,
                blocker=blocker,
            )
        )

    return ExecutiveWorldReadiness(
        tenant_id=snapshot.tenant_id,
        world_snapshot_fingerprint=snapshot.fingerprint,
        as_of=snapshot.as_of,
        fields=tuple(fields),
        ready=not blockers,
        blockers=tuple(blockers),
    )


def diff_world_snapshots(
    *,
    before: WorldSnapshot,
    after: WorldSnapshot,
) -> WorldSnapshotDelta:
    if before.tenant_id != after.tenant_id:
        raise ValueError("world_delta_cross_tenant_forbidden")
    if after.as_of < before.as_of:
        raise ValueError("world_delta_after_predates_before")

    before_map = {(item.entity_id, item.field_name): item for item in before.fields}
    after_map = {(item.entity_id, item.field_name): item for item in after.fields}
    before_blocked = set(before.blocked_field_keys)
    after_blocked = set(after.blocked_field_keys)
    all_keys = set(before_map) | set(after_map) | {
        tuple(item.rsplit(":", 1)) for item in before_blocked | after_blocked
    }
    changes: list[WorldStateChange] = []

    for entity_id, field_name in sorted(all_keys):
        field_key = f"{entity_id}:{field_name}"
        old = before_map.get((entity_id, field_name))
        new = after_map.get((entity_id, field_name))
        was_blocked = field_key in before_blocked
        is_blocked = field_key in after_blocked

        if not was_blocked and is_blocked:
            kind = WorldChangeKind.BLOCKED
        elif was_blocked and not is_blocked:
            kind = WorldChangeKind.UNBLOCKED
        elif old is None and new is not None:
            kind = WorldChangeKind.ADDED
        elif old is not None and new is None:
            kind = WorldChangeKind.REMOVED
        elif old is None or new is None:
            continue
        else:
            old_fp = _value_fingerprint(old.value)
            new_fp = _value_fingerprint(new.value)
            if old_fp != new_fp:
                kind = WorldChangeKind.CHANGED
            elif old.evidence_refs != new.evidence_refs or old.assertion_ids != new.assertion_ids:
                kind = WorldChangeKind.EVIDENCE_REFRESHED
            else:
                continue

        changes.append(
            WorldStateChange(
                field_key=field_key,
                kind=kind,
                before_value_fingerprint=(
                    _value_fingerprint(old.value)
                    if old is not None and not was_blocked
                    else None
                ),
                after_value_fingerprint=(
                    _value_fingerprint(new.value)
                    if new is not None and not is_blocked
                    else None
                ),
                before_assertion_ids=old.assertion_ids if old is not None else (),
                after_assertion_ids=new.assertion_ids if new is not None else (),
                before_evidence_refs=old.evidence_refs if old is not None else (),
                after_evidence_refs=new.evidence_refs if new is not None else (),
            )
        )

    return WorldSnapshotDelta(
        tenant_id=before.tenant_id,
        before_snapshot_fingerprint=before.fingerprint,
        after_snapshot_fingerprint=after.fingerprint,
        before_as_of=before.as_of,
        after_as_of=after.as_of,
        changes=tuple(changes),
        changed_field_keys=tuple(item.field_key for item in changes),
    )
