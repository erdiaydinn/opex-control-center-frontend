"""Decision-facing readiness gates for Jarvis Live Company Reality.

The live-reality ingestion layer decides whether source observations may become
company truth. This module answers the next question: whether the resulting
truth is sufficient for a specific decision or executive claim.

A model cannot waive missing, stale or conflicted required evidence. The gate
returns structured reasons and never manufactures defaults for absent facts.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.live_company_reality import (
    LiveBindingReceipt,
    LiveBindingStatus,
    LiveCompanyRealitySnapshot,
    LiveSourceKind,
)

LIVE_COMPANY_READINESS_CONTRACT = "eay-live-company-readiness-v1"


class SourceTruthReadiness(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


class DecisionTruthStatus(str, Enum):
    PROCEED = "proceed"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class DecisionTruthRequirement(BaseModel):
    requirement_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    required_binding_ids: tuple[str, ...] = ()
    required_field_keys: tuple[str, ...] = ()
    allow_degraded_required_bindings: bool = False

    @model_validator(mode="after")
    def require_truth_surface(self) -> "DecisionTruthRequirement":
        if not self.required_binding_ids and not self.required_field_keys:
            raise ValueError("decision_truth_requirement_must_name_truth")
        if len(set(self.required_binding_ids)) != len(self.required_binding_ids):
            raise ValueError("decision_truth_duplicate_binding_id")
        if len(set(self.required_field_keys)) != len(self.required_field_keys):
            raise ValueError("decision_truth_duplicate_field_key")
        if any(":" not in key for key in self.required_field_keys):
            raise ValueError("decision_truth_field_key_must_include_entity")
        return self


class SourceReadinessReceipt(BaseModel):
    contract: str = LIVE_COMPANY_READINESS_CONTRACT
    binding_id: str
    source_kind: LiveSourceKind
    status: SourceTruthReadiness
    accepted_field_keys: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class DecisionTruthReceipt(BaseModel):
    contract: str = LIVE_COMPANY_READINESS_CONTRACT
    requirement_id: str
    tenant_id: str
    status: DecisionTruthStatus
    source_readiness: tuple[SourceReadinessReceipt, ...]
    missing_required_binding_ids: tuple[str, ...] = ()
    degraded_required_binding_ids: tuple[str, ...] = ()
    stale_required_binding_ids: tuple[str, ...] = ()
    conflicted_required_binding_ids: tuple[str, ...] = ()
    missing_required_field_keys: tuple[str, ...] = ()
    conflicted_required_field_keys: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    firm_claim_authorized: bool = False


def _field_key(receipt: LiveBindingReceipt) -> str | None:
    if receipt.entity_id is None or receipt.field_name is None:
        return None
    return f"{receipt.entity_id}:{receipt.field_name}"


def _source_readiness(
    *,
    binding_id: str,
    receipts: list[LiveBindingReceipt],
    blocked_field_keys: set[str],
) -> SourceReadinessReceipt:
    if not receipts:
        raise ValueError("source_readiness_requires_receipt")

    source_kinds = {receipt.source_kind for receipt in receipts}
    if len(source_kinds) != 1:
        raise ValueError("source_readiness_source_kind_conflict")
    source_kind = next(iter(source_kinds))

    accepted_keys = {
        key
        for receipt in receipts
        if receipt.status is LiveBindingStatus.ACCEPTED
        for key in [_field_key(receipt)]
        if key is not None
    }
    conflicted_keys = sorted(accepted_keys & blocked_field_keys)
    statuses = {receipt.status for receipt in receipts}
    reasons = sorted(
        {
            reason
            for receipt in receipts
            for reason in receipt.reasons
        }
    )

    if conflicted_keys:
        status = SourceTruthReadiness.CONFLICT
        reasons.append("accepted_field_conflict")
    elif LiveBindingStatus.ACCEPTED in statuses:
        if statuses == {LiveBindingStatus.ACCEPTED}:
            status = SourceTruthReadiness.READY
        else:
            status = SourceTruthReadiness.DEGRADED
            reasons.append("binding_has_nonaccepted_observations")
    elif LiveBindingStatus.STALE in statuses:
        status = SourceTruthReadiness.STALE
    else:
        status = SourceTruthReadiness.UNAVAILABLE

    return SourceReadinessReceipt(
        binding_id=binding_id,
        source_kind=source_kind,
        status=status,
        accepted_field_keys=tuple(sorted(accepted_keys)),
        reasons=tuple(sorted(set(reasons))),
    )


def evaluate_decision_truth_readiness(
    *,
    snapshot: LiveCompanyRealitySnapshot,
    requirement: DecisionTruthRequirement,
) -> DecisionTruthReceipt:
    """Evaluate whether live company truth is sufficient for a decision.

    Required sources and fields are explicit. A language model or caller cannot
    reinterpret SOURCE_UNAVAILABLE/STALE/CONFLICT as success.
    """

    if snapshot.tenant_id != requirement.tenant_id:
        raise ValueError("decision_truth_tenant_mismatch")

    blocked_fields = set(snapshot.world.blocked_field_keys)
    receipts_by_binding: dict[str, list[LiveBindingReceipt]] = {}
    for receipt in snapshot.binding_receipts:
        if receipt.tenant_id != requirement.tenant_id:
            raise ValueError("decision_truth_receipt_tenant_mismatch")
        receipts_by_binding.setdefault(receipt.binding_id, []).append(receipt)

    source_readiness = tuple(
        _source_readiness(
            binding_id=binding_id,
            receipts=receipts,
            blocked_field_keys=blocked_fields,
        )
        for binding_id, receipts in sorted(receipts_by_binding.items())
    )
    readiness_by_binding = {
        receipt.binding_id: receipt for receipt in source_readiness
    }

    missing_bindings: list[str] = []
    degraded_bindings: list[str] = []
    stale_bindings: list[str] = []
    conflicted_bindings: list[str] = []

    for binding_id in requirement.required_binding_ids:
        readiness = readiness_by_binding.get(binding_id)
        if readiness is None or readiness.status is SourceTruthReadiness.UNAVAILABLE:
            missing_bindings.append(binding_id)
        elif readiness.status is SourceTruthReadiness.STALE:
            stale_bindings.append(binding_id)
        elif readiness.status is SourceTruthReadiness.CONFLICT:
            conflicted_bindings.append(binding_id)
        elif readiness.status is SourceTruthReadiness.DEGRADED:
            degraded_bindings.append(binding_id)

    available_field_keys = {
        f"{field.entity_id}:{field.field_name}"
        for field in snapshot.world.fields
    }
    required_fields = set(requirement.required_field_keys)
    conflicted_fields = sorted(required_fields & blocked_fields)
    missing_fields = sorted(
        required_fields - available_field_keys - blocked_fields
    )

    hard_fail = bool(
        missing_bindings
        or stale_bindings
        or conflicted_bindings
        or missing_fields
        or conflicted_fields
        or (
            degraded_bindings
            and not requirement.allow_degraded_required_bindings
        )
    )

    reasons: list[str] = []
    if missing_bindings:
        reasons.append("required_source_unavailable")
    if stale_bindings:
        reasons.append("required_source_stale")
    if conflicted_bindings or conflicted_fields:
        reasons.append("required_truth_conflict")
    if missing_fields:
        reasons.append("required_fact_missing")
    if degraded_bindings:
        reasons.append("required_source_degraded")

    optional_nonready = any(
        receipt.binding_id not in requirement.required_binding_ids
        and receipt.status is not SourceTruthReadiness.READY
        for receipt in source_readiness
    )

    if hard_fail:
        status = DecisionTruthStatus.BLOCKED
    elif degraded_bindings or optional_nonready:
        status = DecisionTruthStatus.QUALIFIED
    else:
        status = DecisionTruthStatus.PROCEED

    return DecisionTruthReceipt(
        requirement_id=requirement.requirement_id,
        tenant_id=requirement.tenant_id,
        status=status,
        source_readiness=source_readiness,
        missing_required_binding_ids=tuple(sorted(missing_bindings)),
        degraded_required_binding_ids=tuple(sorted(degraded_bindings)),
        stale_required_binding_ids=tuple(sorted(stale_bindings)),
        conflicted_required_binding_ids=tuple(sorted(conflicted_bindings)),
        missing_required_field_keys=tuple(missing_fields),
        conflicted_required_field_keys=tuple(conflicted_fields),
        reasons=tuple(sorted(set(reasons))),
        firm_claim_authorized=status is DecisionTruthStatus.PROCEED,
    )
