"""Evidence-bound bridge between live external context and Company World.

This module does not turn weather, traffic, events, holidays, outages or other
public context into company truth. It binds verified external observations to a
company-owned location and separately binds governed company metric deviations.
When both are present at the same place/time, Jarvis may open a correlation
review; it still may not assert causality or execute a business action.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .real_world_timeline import (
    RealWorldTimelineEvent,
    TimelineAuthorityClass,
    TimelineEventKind,
)
from .world_model import EntityKind, ResolvedField, TruthClass, WorldSnapshot

COMPANY_WORLD_LIVE_BRIDGE_CONTRACT = "eay-company-world-live-bridge-v1"

_COMPANY_TRUTH_CLASSES = frozenset(
    {TruthClass.GOVERNED_OPERATIONAL, TruthClass.VERIFIED_COMPANY}
)
_EXTERNAL_TRUST_CLASSES = frozenset(
    {TimelineAuthorityClass.VERIFIED_EXTERNAL, TimelineAuthorityClass.VERIFIED_LEGAL}
)
_EXTERNAL_AUTHORITY_PRIORITY = {
    TimelineAuthorityClass.VERIFIED_LEGAL: 90,
    TimelineAuthorityClass.VERIFIED_EXTERNAL: 80,
}
_LOCATION_ENTITY_KINDS = frozenset({EntityKind.STORE, EntityKind.WAREHOUSE})


class ExternalContextDomain(str, Enum):
    WEATHER = "weather"
    TRAFFIC = "traffic"
    TRANSPORT = "transport"
    PUBLIC_EVENT = "public_event"
    PUBLIC_HOLIDAY = "public_holiday"
    UTILITY = "utility"
    SUPPLY_CHAIN = "supply_chain"
    PUBLIC_SAFETY = "public_safety"
    MACROECONOMIC = "macroeconomic"


_DOMAIN_MAX_AGE_SECONDS = {
    ExternalContextDomain.WEATHER: 4 * 60 * 60,
    ExternalContextDomain.TRAFFIC: 60 * 60,
    ExternalContextDomain.TRANSPORT: 4 * 60 * 60,
    ExternalContextDomain.PUBLIC_EVENT: 7 * 24 * 60 * 60,
    ExternalContextDomain.PUBLIC_HOLIDAY: 366 * 24 * 60 * 60,
    ExternalContextDomain.UTILITY: 2 * 60 * 60,
    ExternalContextDomain.SUPPLY_CHAIN: 24 * 60 * 60,
    ExternalContextDomain.PUBLIC_SAFETY: 4 * 60 * 60,
    ExternalContextDomain.MACROECONOMIC: 7 * 24 * 60 * 60,
}


class GeographicScopeLevel(str, Enum):
    COUNTRY = "country"
    REGION = "region"
    LOCALITY = "locality"
    LOCATION = "location"


class CompanyMetricDirection(str, Enum):
    STABLE = "stable"
    INCREASE = "increase"
    DECREASE = "decrease"


class ContextCompanyLinkDisposition(str, Enum):
    NO_APPLICABLE_CONTEXT = "no_applicable_context"
    CONTEXT_ONLY = "context_only"
    CORRELATED_REVIEW_REQUIRED = "correlated_review_required"
    EVIDENCE_CONFLICT = "evidence_conflict"


class GeographicScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: GeographicScopeLevel
    country_code: str = Field(min_length=2, max_length=2)
    region_key: str | None = Field(default=None, min_length=1, max_length=200)
    locality_key: str | None = Field(default=None, min_length=1, max_length=200)
    location_ref: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_scope(self) -> GeographicScope:
        if self.country_code != self.country_code.upper() or not self.country_code.isalpha():
            raise ValueError("company_world_geo_country_code_must_be_upper_alpha2")
        if self.level is GeographicScopeLevel.COUNTRY:
            if self.region_key or self.locality_key or self.location_ref:
                raise ValueError("company_world_country_scope_must_not_narrow")
        elif self.level is GeographicScopeLevel.REGION:
            if not self.region_key or self.locality_key or self.location_ref:
                raise ValueError("company_world_region_scope_invalid")
        elif self.level is GeographicScopeLevel.LOCALITY:
            if not self.region_key or not self.locality_key or self.location_ref:
                raise ValueError("company_world_locality_scope_invalid")
        elif self.level is GeographicScopeLevel.LOCATION and not self.location_ref:
            raise ValueError("company_world_location_scope_requires_location_ref")
        return self


class CompanyLocationBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = COMPANY_WORLD_LIVE_BRIDGE_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    location_entity_id: str = Field(min_length=1)
    world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: GeographicScope
    truth_class: TruthClass
    observed_at: datetime
    evidence_ref: str = Field(min_length=1)
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_binding(self) -> CompanyLocationBinding:
        _aware(self.observed_at, "company_world_location_binding_requires_timezone")
        if self.truth_class not in _COMPANY_TRUTH_CLASSES:
            raise ValueError("company_world_location_binding_requires_company_truth")
        if self.execution_authority_granted:
            raise ValueError("company_world_location_binding_never_grants_execution")
        _verify(self, "company_world_location_binding_fingerprint_mismatch")
        return self


class ExternalContextObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = COMPANY_WORLD_LIVE_BRIDGE_CONTRACT
    observation_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    domain: ExternalContextDomain
    claim_key: str = Field(min_length=1)
    claim_value: Any
    geographic_scope: GeographicScope
    occurred_at: datetime
    observed_at: datetime
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    timeline_event_id: str = Field(min_length=1)
    timeline_event_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_class: TimelineAuthorityClass
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    context_only: bool = True
    company_truth_granted: bool = False
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_observation(self) -> ExternalContextObservation:
        _aware(self.occurred_at, "company_world_external_occurred_at_requires_timezone")
        _aware(self.observed_at, "company_world_external_observed_at_requires_timezone")
        if self.observed_at < self.occurred_at:
            raise ValueError("company_world_external_observed_before_occurrence")
        if self.effective_from is not None:
            _aware(
                self.effective_from,
                "company_world_external_effective_from_requires_timezone",
            )
        if self.effective_until is not None:
            _aware(
                self.effective_until,
                "company_world_external_effective_until_requires_timezone",
            )
            if self.effective_from is None or self.effective_until <= self.effective_from:
                raise ValueError("company_world_external_effective_interval_invalid")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("company_world_external_duplicate_evidence_ref")
        if (
            not self.context_only
            or self.company_truth_granted
            or self.causal_claim_proven
            or self.execution_authority_granted
        ):
            raise ValueError("company_world_external_context_never_grants_company_authority")
        _verify(self, "company_world_external_observation_fingerprint_mismatch")
        return self


class CompanyMetricDeviation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = COMPANY_WORLD_LIVE_BRIDGE_CONTRACT
    tenant_id: str
    company_id: str
    location_entity_id: str
    metric_field_name: str
    previous_world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_value: float
    current_value: float
    direction: CompanyMetricDirection
    deviation_ratio: float = Field(ge=0.0)
    material: bool
    previous_truth_class: TruthClass
    current_truth_class: TruthClass
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_deviation(self) -> CompanyMetricDeviation:
        if (
            self.previous_truth_class not in _COMPANY_TRUTH_CLASSES
            or self.current_truth_class not in _COMPANY_TRUTH_CLASSES
        ):
            raise ValueError("company_world_metric_deviation_requires_company_truth")
        if not math.isfinite(self.previous_value) or not math.isfinite(self.current_value):
            raise ValueError("company_world_metric_deviation_requires_finite_values")
        if self.causal_claim_proven or self.execution_authority_granted:
            raise ValueError("company_world_metric_deviation_never_grants_causal_authority")
        _verify(self, "company_world_metric_deviation_fingerprint_mismatch")
        return self


class ContextObservationState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str
    trusted_authority: bool
    fresh: bool
    geography_match: bool
    temporally_relevant: bool
    applicable: bool
    blocker: str | None = None


class CompanyWorldLivePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lookahead_seconds: int = Field(default=86_400, ge=0, le=31_536_000)


class ContextCompanyLinkReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = COMPANY_WORLD_LIVE_BRIDGE_CONTRACT
    tenant_id: str
    company_id: str
    as_of: datetime
    current_world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    location_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_states: tuple[ContextObservationState, ...]
    applicable_observation_fingerprints: tuple[str, ...]
    material_deviation_fingerprints: tuple[str, ...]
    disposition: ContextCompanyLinkDisposition
    reason_codes: tuple[str, ...] = Field(min_length=1)
    company_operational_deviation_authorized: bool
    context_coincident_with_company_deviation: bool
    causal_claim_proven: bool = False
    firm_company_causal_claim_authorized: bool = False
    automatic_action_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ContextCompanyLinkReceipt:
        _aware(self.as_of, "company_world_link_as_of_requires_timezone")
        if (
            self.causal_claim_proven
            or self.firm_company_causal_claim_authorized
            or self.automatic_action_allowed
            or self.execution_authority_granted
        ):
            raise ValueError("company_world_link_never_grants_causal_or_action_authority")
        if self.context_coincident_with_company_deviation and (
            not self.applicable_observation_fingerprints
            or not self.material_deviation_fingerprints
        ):
            raise ValueError("company_world_link_coincidence_requires_both_evidence_families")
        _verify(self, "company_world_link_receipt_fingerprint_mismatch")
        return self


def build_company_location_binding(
    *,
    world: WorldSnapshot,
    company_id: str,
    location_entity_id: str,
    scope: GeographicScope,
    truth_class: TruthClass,
    observed_at: datetime,
    evidence_ref: str,
) -> CompanyLocationBinding:
    current = WorldSnapshot.model_validate(world.model_dump(mode="json"))
    _aware(observed_at, "company_world_location_binding_requires_timezone")
    if observed_at > current.as_of:
        raise ValueError("company_world_location_binding_newer_than_world")
    entity = next(
        (item for item in current.entities if item.entity_id == location_entity_id),
        None,
    )
    if entity is None:
        raise ValueError("company_world_location_entity_missing")
    if entity.kind not in _LOCATION_ENTITY_KINDS:
        raise ValueError("company_world_location_entity_kind_invalid")
    if scope.level is GeographicScopeLevel.LOCATION and scope.location_ref != location_entity_id:
        raise ValueError("company_world_location_scope_entity_mismatch")
    return _seal(
        CompanyLocationBinding,
        {
            "contract": COMPANY_WORLD_LIVE_BRIDGE_CONTRACT,
            "tenant_id": current.tenant_id,
            "company_id": company_id,
            "location_entity_id": location_entity_id,
            "world_fingerprint": current.fingerprint,
            "scope": scope,
            "truth_class": truth_class,
            "observed_at": observed_at,
            "evidence_ref": evidence_ref,
            "execution_authority_granted": False,
        },
    )


def build_external_context_observation(
    *,
    event: RealWorldTimelineEvent,
    observation_id: str,
    domain: ExternalContextDomain,
    claim_key: str,
    claim_value: Any,
    geographic_scope: GeographicScope,
) -> ExternalContextObservation:
    validated = RealWorldTimelineEvent.model_validate(event.model_dump(mode="json"))
    if validated.event_kind not in {
        TimelineEventKind.EXTERNAL_CONTEXT,
        TimelineEventKind.AMBIENT_OBSERVATION,
    }:
        raise ValueError("company_world_external_observation_requires_context_event")
    return _seal(
        ExternalContextObservation,
        {
            "contract": COMPANY_WORLD_LIVE_BRIDGE_CONTRACT,
            "observation_id": observation_id,
            "tenant_id": validated.tenant_id,
            "domain": domain,
            "claim_key": claim_key,
            "claim_value": claim_value,
            "geographic_scope": geographic_scope,
            "occurred_at": validated.occurred_at,
            "observed_at": validated.observed_at,
            "effective_from": validated.effective_from,
            "effective_until": validated.effective_until,
            "timeline_event_id": validated.event_id,
            "timeline_event_fingerprint": validated.fingerprint,
            "authority_class": validated.authority_class,
            "confidence": validated.confidence,
            "evidence_refs": validated.evidence_refs,
            "context_only": True,
            "company_truth_granted": False,
            "causal_claim_proven": False,
            "execution_authority_granted": False,
        },
    )


def build_company_metric_deviation(
    *,
    previous_world: WorldSnapshot,
    current_world: WorldSnapshot,
    company_id: str,
    location_entity_id: str,
    metric_field_name: str,
    material_change_ratio: float = 0.10,
) -> CompanyMetricDeviation:
    if material_change_ratio < 0.0:
        raise ValueError("company_world_material_change_ratio_must_be_non_negative")
    previous = WorldSnapshot.model_validate(previous_world.model_dump(mode="json"))
    current = WorldSnapshot.model_validate(current_world.model_dump(mode="json"))
    if previous.tenant_id != current.tenant_id:
        raise ValueError("company_world_metric_cross_tenant_world_forbidden")
    if previous.as_of > current.as_of:
        raise ValueError("company_world_metric_world_time_regression")
    field_key = f"{location_entity_id}:{metric_field_name}"
    if field_key in previous.blocked_field_keys or field_key in current.blocked_field_keys:
        raise ValueError("company_world_metric_field_contradicted")
    previous_field = _resolved_field(previous, location_entity_id, metric_field_name)
    current_field = _resolved_field(current, location_entity_id, metric_field_name)
    previous_value = _numeric_value(previous_field)
    current_value = _numeric_value(current_field)
    denominator = max(abs(previous_value), 1.0)
    ratio = abs(current_value - previous_value) / denominator
    if current_value > previous_value:
        direction = CompanyMetricDirection.INCREASE
    elif current_value < previous_value:
        direction = CompanyMetricDirection.DECREASE
    else:
        direction = CompanyMetricDirection.STABLE
    return _seal(
        CompanyMetricDeviation,
        {
            "contract": COMPANY_WORLD_LIVE_BRIDGE_CONTRACT,
            "tenant_id": current.tenant_id,
            "company_id": company_id,
            "location_entity_id": location_entity_id,
            "metric_field_name": metric_field_name,
            "previous_world_fingerprint": previous.fingerprint,
            "current_world_fingerprint": current.fingerprint,
            "previous_value": previous_value,
            "current_value": current_value,
            "direction": direction,
            "deviation_ratio": round(ratio, 6),
            "material": ratio >= material_change_ratio,
            "previous_truth_class": previous_field.truth_class,
            "current_truth_class": current_field.truth_class,
            "evidence_refs": tuple(
                sorted({*previous_field.evidence_refs, *current_field.evidence_refs})
            ),
            "causal_claim_proven": False,
            "execution_authority_granted": False,
        },
    )


def assess_company_world_live_context(
    *,
    tenant_id: str,
    company_id: str,
    as_of: datetime,
    current_world: WorldSnapshot,
    location_binding: CompanyLocationBinding,
    observations: tuple[ExternalContextObservation, ...] = (),
    deviations: tuple[CompanyMetricDeviation, ...] = (),
    policy: CompanyWorldLivePolicy | None = None,
) -> ContextCompanyLinkReceipt:
    _aware(as_of, "company_world_link_as_of_requires_timezone")
    world = WorldSnapshot.model_validate(current_world.model_dump(mode="json"))
    binding = CompanyLocationBinding.model_validate(location_binding.model_dump(mode="json"))
    if world.tenant_id != tenant_id:
        raise ValueError("company_world_link_world_tenant_mismatch")
    if world.as_of > as_of:
        raise ValueError("company_world_link_world_from_future")
    if binding.tenant_id != tenant_id or binding.company_id != company_id:
        raise ValueError("company_world_link_location_identity_mismatch")
    if binding.world_fingerprint != world.fingerprint:
        raise ValueError("company_world_link_location_binding_world_stale")
    rules = policy or CompanyWorldLivePolicy()

    states: list[ContextObservationState] = []
    applicable: list[ExternalContextObservation] = []
    for raw in observations:
        observation = ExternalContextObservation.model_validate(raw.model_dump(mode="json"))
        if observation.tenant_id != tenant_id:
            raise ValueError("company_world_link_cross_tenant_external_context")
        if observation.observed_at > as_of:
            raise ValueError("company_world_link_external_context_from_future")
        trusted = observation.authority_class in _EXTERNAL_TRUST_CLASSES
        age_seconds = (as_of - observation.observed_at).total_seconds()
        fresh = age_seconds <= _DOMAIN_MAX_AGE_SECONDS[observation.domain]
        geography_match = _scope_applies(
            observation.geographic_scope,
            binding.scope,
            binding.location_entity_id,
        )
        temporal = _temporally_relevant(observation, as_of, rules.lookahead_seconds)
        is_applicable = trusted and fresh and geography_match and temporal
        blocker: str | None = None
        if not trusted:
            blocker = "company_world_external_authority_insufficient"
        elif not fresh:
            blocker = "company_world_external_context_stale"
        elif not geography_match:
            blocker = "company_world_external_geography_mismatch"
        elif not temporal:
            blocker = "company_world_external_not_temporally_relevant"
        states.append(
            ContextObservationState(
                observation_id=observation.observation_id,
                trusted_authority=trusted,
                fresh=fresh,
                geography_match=geography_match,
                temporally_relevant=temporal,
                applicable=is_applicable,
                blocker=blocker,
            )
        )
        if is_applicable:
            applicable.append(observation)

    material_deviations: list[CompanyMetricDeviation] = []
    for raw in deviations:
        deviation = CompanyMetricDeviation.model_validate(raw.model_dump(mode="json"))
        if deviation.tenant_id != tenant_id or deviation.company_id != company_id:
            raise ValueError("company_world_link_metric_identity_mismatch")
        if deviation.location_entity_id != binding.location_entity_id:
            raise ValueError("company_world_link_metric_location_mismatch")
        if deviation.current_world_fingerprint != world.fingerprint:
            raise ValueError("company_world_link_metric_world_stale")
        if deviation.material:
            material_deviations.append(deviation)

    conflict = _external_conflict(applicable)
    company_deviation = bool(material_deviations)
    coincident = bool(applicable) and company_deviation
    reasons: list[str] = []
    if conflict:
        disposition = ContextCompanyLinkDisposition.EVIDENCE_CONFLICT
        reasons.append("company_world_external_context_conflict")
    elif not applicable:
        disposition = ContextCompanyLinkDisposition.NO_APPLICABLE_CONTEXT
        reasons.append("company_world_no_verified_applicable_external_context")
    elif company_deviation:
        disposition = ContextCompanyLinkDisposition.CORRELATED_REVIEW_REQUIRED
        reasons.extend(
            (
                "company_world_verified_external_context_applicable",
                "company_world_governed_operational_deviation_observed",
                "company_world_correlation_is_not_causality",
            )
        )
    else:
        disposition = ContextCompanyLinkDisposition.CONTEXT_ONLY
        reasons.extend(
            (
                "company_world_verified_external_context_applicable",
                "company_world_no_material_operational_deviation_observed",
            )
        )

    return _seal(
        ContextCompanyLinkReceipt,
        {
            "contract": COMPANY_WORLD_LIVE_BRIDGE_CONTRACT,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "as_of": as_of,
            "current_world_fingerprint": world.fingerprint,
            "location_binding_fingerprint": binding.fingerprint,
            "observation_states": tuple(states),
            "applicable_observation_fingerprints": tuple(
                sorted(item.fingerprint for item in applicable)
            ),
            "material_deviation_fingerprints": tuple(
                sorted(item.fingerprint for item in material_deviations)
            ),
            "disposition": disposition,
            "reason_codes": tuple(dict.fromkeys(reasons)),
            "company_operational_deviation_authorized": company_deviation,
            "context_coincident_with_company_deviation": coincident,
            "causal_claim_proven": False,
            "firm_company_causal_claim_authorized": False,
            "automatic_action_allowed": False,
            "execution_authority_granted": False,
        },
    )


def _resolved_field(
    world: WorldSnapshot,
    location_entity_id: str,
    metric_field_name: str,
) -> ResolvedField:
    entity = next((item for item in world.entities if item.entity_id == location_entity_id), None)
    if entity is None:
        raise ValueError("company_world_metric_location_missing")
    if entity.kind not in _LOCATION_ENTITY_KINDS:
        raise ValueError("company_world_metric_location_kind_invalid")
    field = next(
        (
            item
            for item in world.fields
            if item.entity_id == location_entity_id and item.field_name == metric_field_name
        ),
        None,
    )
    if field is None:
        raise ValueError("company_world_metric_field_missing")
    if field.truth_class not in _COMPANY_TRUTH_CLASSES:
        raise ValueError("company_world_metric_deviation_requires_company_truth")
    return field


def _numeric_value(field: ResolvedField) -> float:
    if isinstance(field.value, bool) or not isinstance(field.value, (int, float)):
        raise TypeError("company_world_metric_deviation_requires_numeric_values")
    value = float(field.value)
    if not math.isfinite(value):
        raise ValueError("company_world_metric_deviation_requires_finite_values")
    return value


def _scope_applies(
    external: GeographicScope,
    company: GeographicScope,
    location_entity_id: str,
) -> bool:
    if external.country_code != company.country_code:
        return False
    if external.level is GeographicScopeLevel.COUNTRY:
        return True
    if external.region_key != company.region_key:
        return False
    if external.level is GeographicScopeLevel.REGION:
        return True
    if external.locality_key != company.locality_key:
        return False
    if external.level is GeographicScopeLevel.LOCALITY:
        return True
    return external.location_ref == location_entity_id


def _temporally_relevant(
    observation: ExternalContextObservation,
    as_of: datetime,
    lookahead_seconds: int,
) -> bool:
    effective_from = observation.effective_from
    effective_until = observation.effective_until
    if effective_until is not None and as_of >= effective_until:
        return False
    if effective_from is None:
        return observation.occurred_at <= as_of
    if effective_from <= as_of:
        return True
    return effective_from <= as_of + timedelta(seconds=lookahead_seconds)


def _external_conflict(observations: list[ExternalContextObservation]) -> bool:
    grouped: dict[tuple[ExternalContextDomain, str], list[ExternalContextObservation]] = {}
    for observation in observations:
        grouped.setdefault((observation.domain, observation.claim_key), []).append(observation)
    for candidates in grouped.values():
        highest = max(_EXTERNAL_AUTHORITY_PRIORITY[item.authority_class] for item in candidates)
        top = [
            item
            for item in candidates
            if _EXTERNAL_AUTHORITY_PRIORITY[item.authority_class] == highest
        ]
        values = {_canonical_value(item.claim_value) for item in top}
        if len(values) > 1:
            return True
    return False


def _canonical_value(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _seal(model_class: type[BaseModel], values: dict[str, Any]):
    draft = model_class.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_class.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
