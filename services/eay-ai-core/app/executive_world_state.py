"""Decision-relevant views over the canonical EAY Company World Model.

The canonical :mod:`world_model` remains the source of company state. This
module does not create a second world store. It derives bounded executive views:
small relation-aware subgraphs, explicit required-field readiness, and
fingerprint-only snapshot changes suitable for reasoning and audit.

Raw company values stay in the canonical WorldSnapshot/subgraph. Diff records
carry value fingerprints rather than copying business payloads into another
memory layer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .world_model import WorldAssertion, WorldEntity, WorldSnapshot, build_world_snapshot

EXECUTIVE_WORLD_STATE_CONTRACT = "eay-executive-world-state-v1"


class WorldRequirementStatus(str, Enum):
    READY = "ready"
    MISSING = "missing"
    BLOCKED = "blocked"
    STALE = "stale"


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


class ExecutiveFieldReadiness(BaseModel):
    entity_id: str
    field_name: str
    status: WorldRequirementStatus
    assertion_id: str | None = None
    truth_class: str | None = None
    observed_at: datetime | None = None
    evidence_ref: str | None = None
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


class WorldStateChange(BaseModel):
    field_key: str
    kind: WorldChangeKind
    before_value_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    after_value_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    before_assertion_id: str | None = None
    after_assertion_id: str | None = None
    before_evidence_ref: str | None = None
    after_evidence_ref: str | None = None


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


def build_decision_subgraph(
    *,
    snapshot: WorldSnapshot,
    seed_entity_ids: tuple[str, ...],
    relationship_hops: int = 1,
    field_allowlist: tuple[str, ...] = (),
) -> WorldSnapshot:
    """Return a canonical WorldSnapshot narrowed to decision-relevant entities.

    Relationships are followed only when their opaque reference exactly matches
    another entity ID in the same snapshot. No invented graph edge is inferred.
    """

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
        for entity_id in frontier:
            for relationship in entity_map[entity_id].relationships:
                if relationship in entity_map and relationship not in selected:
                    next_frontier.add(relationship)
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier

    allowed_fields = set(field_allowlist)
    entities = [item for item in snapshot.entities if item.entity_id in selected]
    assertions = [
        item
        for item in snapshot.assertions
        if item.entity_id in selected and (not allowed_fields or item.field_name in allowed_fields)
    ]
    return build_world_snapshot(
        tenant_id=snapshot.tenant_id,
        as_of=snapshot.as_of,
        entities=entities,
        assertions=assertions,
    )


def assess_executive_world_readiness(
    *,
    snapshot: WorldSnapshot,
    requirements: tuple[ExecutiveFieldRequirement, ...],
) -> ExecutiveWorldReadiness:
    if not requirements:
        raise ValueError("executive_world_readiness_requires_fields")
    identities = [(item.entity_id, item.field_name) for item in requirements]
    if len(identities) != len(set(identities)):
        raise ValueError("executive_world_readiness_duplicate_requirement")

    resolved = {
        (item.entity_id, item.field_name): item
        for item in snapshot.assertions
        if f"{item.entity_id}:{item.field_name}" not in snapshot.blocked_field_keys
    }
    blocked = set(snapshot.blocked_field_keys)
    fields: list[ExecutiveFieldReadiness] = []
    blockers: list[str] = []

    for requirement in requirements:
        key = (requirement.entity_id, requirement.field_name)
        field_key = f"{requirement.entity_id}:{requirement.field_name}"
        assertion = resolved.get(key)
        if field_key in blocked:
            status = WorldRequirementStatus.BLOCKED
            blocker = f"world_field_blocked:{field_key}"
            blockers.append(blocker)
            fields.append(
                ExecutiveFieldReadiness(
                    entity_id=requirement.entity_id,
                    field_name=requirement.field_name,
                    status=status,
                    blocker=blocker,
                )
            )
            continue
        if assertion is None:
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

        stale = False
        if requirement.maximum_observation_age_seconds is not None:
            age_seconds = (snapshot.as_of - assertion.observed_at).total_seconds()
            stale = age_seconds > requirement.maximum_observation_age_seconds
        if stale:
            blocker = f"world_field_stale:{field_key}"
            blockers.append(blocker)
            status = WorldRequirementStatus.STALE
        else:
            blocker = None
            status = WorldRequirementStatus.READY
        fields.append(
            ExecutiveFieldReadiness(
                entity_id=requirement.entity_id,
                field_name=requirement.field_name,
                status=status,
                assertion_id=assertion.assertion_id,
                truth_class=assertion.truth_class.value,
                observed_at=assertion.observed_at,
                evidence_ref=assertion.evidence_ref,
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

    before_map = {(item.entity_id, item.field_name): item for item in before.assertions}
    after_map = {(item.entity_id, item.field_name): item for item in after.assertions}
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
            elif old.evidence_ref != new.evidence_ref or old.assertion_id != new.assertion_id:
                kind = WorldChangeKind.EVIDENCE_REFRESHED
            else:
                continue

        changes.append(
            WorldStateChange(
                field_key=field_key,
                kind=kind,
                before_value_fingerprint=_value_fingerprint(old.value) if old is not None else None,
                after_value_fingerprint=_value_fingerprint(new.value) if new is not None else None,
                before_assertion_id=old.assertion_id if old is not None else None,
                after_assertion_id=new.assertion_id if new is not None else None,
                before_evidence_ref=old.evidence_ref if old is not None else None,
                after_evidence_ref=new.evidence_ref if new is not None else None,
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
