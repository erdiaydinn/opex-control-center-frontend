"""Evidence-bound engine efficiency learning for Jarvis local-first routing.

Benchmark evidence remains the quality/safety gate. This module never rewrites a
benchmark score and never grants execution authority. It records secret-safe invocation
outcomes (success, latency and observed provider cost) in an append-only tenant ledger,
then allows efficiency to break ties only inside a narrow, policy-bounded quality band.

Historical routing is time-correct: both ``observed_at`` and ``recorded_at`` must be at
or before the routing cutoff. Future telemetry therefore cannot leak into replay. A
candidate with insufficient samples remains neutral; by default every candidate in the
quality band must have enough evidence before efficiency can change the canonical local
model selection. This avoids rewarding a lightly sampled model over a well-observed one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from statistics import median_low

from pydantic import BaseModel, Field, model_validator

from .engine_gateway import EngineInvocationReceipt
from .local_model_pool import (
    LocalModelCatalog,
    LocalModelDeployment,
    LocalModelSelection,
    LocalModelTask,
    select_local_model,
)
from .paid_token_governance import PaidTokenUsageReceipt

ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT = "eay-engine-efficiency-intelligence-v1"


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _secret_safe_ref(value: str | None) -> bool:
    if value is None:
        return True
    lowered = value.casefold()
    forbidden = (
        "api_key=",
        "apikey=",
        "authorization:",
        "bearer ",
        "password=",
        "secret=",
        "token=",
    )
    return not any(marker in lowered for marker in forbidden)


class EngineEfficiencyObservation(BaseModel):
    contract: str = ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT
    observation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    engine_id: str = Field(min_length=1)
    task_class: str = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    succeeded: bool
    latency_ms: int = Field(ge=0, le=3_600_000)
    paid_execution: bool = False
    cost_observed: bool = False
    provider_cost_microunits: int = Field(default=0, ge=0)
    billable_microunits: int = Field(default=0, ge=0)
    invocation_evidence_ref: str = Field(min_length=1)
    paid_usage_ref: str | None = None
    provider_response_ref: str | None = None
    raw_prompt_retained: bool = False
    raw_payload_retained: bool = False
    secret_values_retained: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_integrity_bound_and_non_authoritative(self) -> "EngineEfficiencyObservation":
        _aware(self.observed_at, "engine_efficiency_observed_at_requires_timezone")
        _aware(self.recorded_at, "engine_efficiency_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("engine_efficiency_recorded_at_precedes_observation")
        if self.raw_prompt_retained or self.raw_payload_retained or self.secret_values_retained:
            raise ValueError("engine_efficiency_cannot_retain_raw_sensitive_content")
        if self.execution_authority_granted:
            raise ValueError("engine_efficiency_never_grants_execution_authority")
        for ref in (
            self.invocation_evidence_ref,
            self.paid_usage_ref,
            self.provider_response_ref,
        ):
            if not _secret_safe_ref(ref):
                raise ValueError("engine_efficiency_secret_bearing_reference_forbidden")
        if not self.paid_execution:
            if self.paid_usage_ref is not None:
                raise ValueError("engine_efficiency_local_observation_cannot_claim_paid_usage")
            if self.provider_cost_microunits or self.billable_microunits:
                raise ValueError("engine_efficiency_local_observation_must_have_zero_provider_cost")
        if self.paid_usage_ref is not None and not self.paid_execution:
            raise ValueError("engine_efficiency_paid_usage_requires_paid_execution")
        if self.cost_observed and self.paid_execution and self.paid_usage_ref is None:
            raise ValueError("engine_efficiency_paid_cost_requires_usage_receipt")
        if not self.cost_observed and (
            self.provider_cost_microunits or self.billable_microunits
        ):
            raise ValueError("engine_efficiency_unobserved_cost_must_be_zero")
        if self.fingerprint != _hash(_observation_payload(self)):
            raise ValueError("engine_efficiency_observation_fingerprint_mismatch")
        return self


def _observation_payload(observation: EngineEfficiencyObservation) -> dict[str, object]:
    return {
        "contract": observation.contract,
        "observation_id": observation.observation_id,
        "tenant_id": observation.tenant_id,
        "engine_id": observation.engine_id,
        "task_class": observation.task_class,
        "observed_at": observation.observed_at.isoformat(),
        "recorded_at": observation.recorded_at.isoformat(),
        "succeeded": observation.succeeded,
        "latency_ms": observation.latency_ms,
        "paid_execution": observation.paid_execution,
        "cost_observed": observation.cost_observed,
        "provider_cost_microunits": observation.provider_cost_microunits,
        "billable_microunits": observation.billable_microunits,
        "invocation_evidence_ref": observation.invocation_evidence_ref,
        "paid_usage_ref": observation.paid_usage_ref,
        "provider_response_ref": observation.provider_response_ref,
        "raw_prompt_retained": False,
        "raw_payload_retained": False,
        "secret_values_retained": False,
        "execution_authority_granted": False,
    }


def _observation_id(
    *,
    tenant_id: str,
    engine_id: str,
    task_class: str,
    observed_at: datetime,
    invocation_evidence_ref: str,
) -> str:
    return _hash(
        {
            "tenant_id": tenant_id,
            "engine_id": engine_id,
            "task_class": task_class,
            "observed_at": observed_at.isoformat(),
            "invocation_evidence_ref": invocation_evidence_ref,
        }
    )


def record_engine_efficiency_observation(
    *,
    tenant_id: str,
    engine_id: str,
    task_class: str,
    observed_at: datetime,
    recorded_at: datetime,
    succeeded: bool,
    latency_ms: int,
    invocation_evidence_ref: str,
    paid_execution: bool = False,
    cost_observed: bool = False,
    provider_cost_microunits: int = 0,
    billable_microunits: int = 0,
    paid_usage_ref: str | None = None,
    provider_response_ref: str | None = None,
) -> EngineEfficiencyObservation:
    _aware(observed_at, "engine_efficiency_observed_at_requires_timezone")
    _aware(recorded_at, "engine_efficiency_recorded_at_requires_timezone")
    observation_id = _observation_id(
        tenant_id=tenant_id,
        engine_id=engine_id,
        task_class=task_class,
        observed_at=observed_at,
        invocation_evidence_ref=invocation_evidence_ref,
    )
    provisional = EngineEfficiencyObservation.model_construct(
        contract=ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT,
        observation_id=observation_id,
        tenant_id=tenant_id,
        engine_id=engine_id,
        task_class=task_class,
        observed_at=observed_at,
        recorded_at=recorded_at,
        succeeded=succeeded,
        latency_ms=latency_ms,
        paid_execution=paid_execution,
        cost_observed=cost_observed,
        provider_cost_microunits=provider_cost_microunits,
        billable_microunits=billable_microunits,
        invocation_evidence_ref=invocation_evidence_ref,
        paid_usage_ref=paid_usage_ref,
        provider_response_ref=provider_response_ref,
        raw_prompt_retained=False,
        raw_payload_retained=False,
        secret_values_retained=False,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return EngineEfficiencyObservation(
        observation_id=observation_id,
        tenant_id=tenant_id,
        engine_id=engine_id,
        task_class=task_class,
        observed_at=observed_at,
        recorded_at=recorded_at,
        succeeded=succeeded,
        latency_ms=latency_ms,
        paid_execution=paid_execution,
        cost_observed=cost_observed,
        provider_cost_microunits=provider_cost_microunits,
        billable_microunits=billable_microunits,
        invocation_evidence_ref=invocation_evidence_ref,
        paid_usage_ref=paid_usage_ref,
        provider_response_ref=provider_response_ref,
        fingerprint=_hash(_observation_payload(provisional)),
    )


def successful_engine_efficiency_observation(
    *,
    tenant_id: str,
    task_class: str,
    receipt: EngineInvocationReceipt,
    observed_at: datetime,
    recorded_at: datetime,
    latency_ms: int,
    invocation_evidence_ref: str,
    paid_usage: PaidTokenUsageReceipt | None = None,
) -> EngineEfficiencyObservation:
    paid_execution = receipt.external_processing
    if paid_execution != (paid_usage is not None):
        raise ValueError("engine_efficiency_external_receipt_paid_usage_mismatch")
    if paid_usage is not None:
        if paid_usage.provider != receipt.provider.value or paid_usage.model_id != receipt.model_id:
            raise ValueError("engine_efficiency_paid_usage_engine_identity_mismatch")
        if (
            paid_usage.provider_response_ref is not None
            and receipt.provider_response_id is not None
            and paid_usage.provider_response_ref != receipt.provider_response_id
        ):
            raise ValueError("engine_efficiency_provider_response_identity_mismatch")
    return record_engine_efficiency_observation(
        tenant_id=tenant_id,
        engine_id=receipt.engine_id,
        task_class=task_class,
        observed_at=observed_at,
        recorded_at=recorded_at,
        succeeded=True,
        latency_ms=latency_ms,
        invocation_evidence_ref=invocation_evidence_ref,
        paid_execution=paid_execution,
        cost_observed=True,
        provider_cost_microunits=(
            0 if paid_usage is None else paid_usage.provider_cost_microunits
        ),
        billable_microunits=0 if paid_usage is None else paid_usage.billable_microunits,
        paid_usage_ref=None if paid_usage is None else paid_usage.usage_ref,
        provider_response_ref=receipt.provider_response_id,
    )


class EngineEfficiencyLedgerSnapshot(BaseModel):
    contract: str = ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT
    tenant_id: str = Field(min_length=1)
    generated_at: datetime
    observations: tuple[EngineEfficiencyObservation, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ledger_is_tenant_bound_and_integrity_sealed(self) -> "EngineEfficiencyLedgerSnapshot":
        _aware(self.generated_at, "engine_efficiency_ledger_generated_at_requires_timezone")
        ids: list[str] = []
        for item in self.observations:
            validated = EngineEfficiencyObservation.model_validate(item.model_dump(mode="json"))
            if validated.tenant_id != self.tenant_id:
                raise ValueError("engine_efficiency_cross_tenant_observation_forbidden")
            ids.append(validated.observation_id)
        if len(ids) != len(set(ids)):
            raise ValueError("engine_efficiency_observation_ids_must_be_unique")
        if self.fingerprint != _ledger_fingerprint(
            tenant_id=self.tenant_id,
            generated_at=self.generated_at,
            observations=self.observations,
        ):
            raise ValueError("engine_efficiency_ledger_fingerprint_mismatch")
        return self


def _ledger_fingerprint(
    *,
    tenant_id: str,
    generated_at: datetime,
    observations: tuple[EngineEfficiencyObservation, ...],
) -> str:
    return _hash(
        {
            "contract": ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT,
            "tenant_id": tenant_id,
            "generated_at": generated_at.isoformat(),
            "observations": [
                (item.observation_id, item.fingerprint) for item in observations
            ],
        }
    )


def _build_ledger(
    *,
    tenant_id: str,
    generated_at: datetime,
    observations: tuple[EngineEfficiencyObservation, ...],
) -> EngineEfficiencyLedgerSnapshot:
    ordered = tuple(
        sorted(observations, key=lambda item: (item.recorded_at, item.observation_id))
    )
    return EngineEfficiencyLedgerSnapshot(
        tenant_id=tenant_id,
        generated_at=generated_at,
        observations=ordered,
        fingerprint=_ledger_fingerprint(
            tenant_id=tenant_id,
            generated_at=generated_at,
            observations=ordered,
        ),
    )


def new_engine_efficiency_ledger(
    *, tenant_id: str, generated_at: datetime
) -> EngineEfficiencyLedgerSnapshot:
    _aware(generated_at, "engine_efficiency_ledger_generated_at_requires_timezone")
    return _build_ledger(
        tenant_id=tenant_id,
        generated_at=generated_at,
        observations=(),
    )


def append_engine_efficiency_observation(
    *,
    ledger: EngineEfficiencyLedgerSnapshot,
    observation: EngineEfficiencyObservation,
) -> EngineEfficiencyLedgerSnapshot:
    ledger = EngineEfficiencyLedgerSnapshot.model_validate(ledger.model_dump(mode="json"))
    observation = EngineEfficiencyObservation.model_validate(
        observation.model_dump(mode="json")
    )
    if observation.tenant_id != ledger.tenant_id:
        raise ValueError("engine_efficiency_cross_tenant_observation_forbidden")
    existing = next(
        (
            item
            for item in ledger.observations
            if item.observation_id == observation.observation_id
        ),
        None,
    )
    if existing is not None:
        if existing.fingerprint == observation.fingerprint:
            return ledger
        raise ValueError("engine_efficiency_observation_identity_conflict")
    return _build_ledger(
        tenant_id=ledger.tenant_id,
        generated_at=max(ledger.generated_at, observation.recorded_at),
        observations=(*ledger.observations, observation),
    )


class EngineEfficiencyPreference(BaseModel):
    contract: str = ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT
    tenant_id: str
    task_class: str
    engine_id: str
    sample_count: int = Field(ge=0)
    success_rate_basis_points: int = Field(ge=0, le=10_000)
    p50_latency_ms: int | None = Field(default=None, ge=0)
    cost_sample_count: int = Field(ge=0)
    average_provider_cost_microunits: int | None = Field(default=None, ge=0)
    enough_samples: bool
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def preference_never_becomes_execution_authority(self) -> "EngineEfficiencyPreference":
        if self.execution_authority_granted:
            raise ValueError("engine_efficiency_preference_never_grants_execution_authority")
        if self.sample_count == 0 and (
            self.p50_latency_ms is not None or self.cost_sample_count
        ):
            raise ValueError("engine_efficiency_empty_preference_has_metrics")
        if self.cost_sample_count == 0 and self.average_provider_cost_microunits is not None:
            raise ValueError("engine_efficiency_cost_average_requires_cost_samples")
        return self


def build_engine_efficiency_preferences(
    *,
    ledger: EngineEfficiencyLedgerSnapshot,
    tenant_id: str,
    task_class: str,
    engine_ids: tuple[str, ...],
    as_of: datetime,
    min_samples: int = 5,
) -> tuple[EngineEfficiencyPreference, ...]:
    if min_samples < 1:
        raise ValueError("engine_efficiency_min_samples_must_be_positive")
    _aware(as_of, "engine_efficiency_preference_as_of_requires_timezone")
    ledger = EngineEfficiencyLedgerSnapshot.model_validate(ledger.model_dump(mode="json"))
    if ledger.tenant_id != tenant_id:
        raise ValueError("engine_efficiency_ledger_tenant_mismatch")
    if len(engine_ids) != len(set(engine_ids)):
        raise ValueError("engine_efficiency_preference_engine_ids_must_be_unique")

    preferences: list[EngineEfficiencyPreference] = []
    for engine_id in engine_ids:
        samples = [
            item
            for item in ledger.observations
            if item.engine_id == engine_id
            and item.task_class == task_class
            and item.observed_at <= as_of
            and item.recorded_at <= as_of
        ]
        success_count = sum(1 for item in samples if item.succeeded)
        cost_samples = [item for item in samples if item.cost_observed]
        preferences.append(
            EngineEfficiencyPreference(
                tenant_id=tenant_id,
                task_class=task_class,
                engine_id=engine_id,
                sample_count=len(samples),
                success_rate_basis_points=(
                    0 if not samples else success_count * 10_000 // len(samples)
                ),
                p50_latency_ms=(
                    None
                    if not samples
                    else int(median_low([item.latency_ms for item in samples]))
                ),
                cost_sample_count=len(cost_samples),
                average_provider_cost_microunits=(
                    None
                    if not cost_samples
                    else sum(item.provider_cost_microunits for item in cost_samples)
                    // len(cost_samples)
                ),
                enough_samples=len(samples) >= min_samples,
            )
        )
    return tuple(preferences)


class EngineEfficiencyRoutingPolicy(BaseModel):
    contract: str = ENGINE_EFFICIENCY_INTELLIGENCE_CONTRACT
    min_samples_per_candidate: int = Field(default=5, ge=1, le=10_000)
    max_benchmark_delta: float = Field(default=0.02, ge=0.0, le=0.10)
    require_complete_quality_band: bool = True


def select_local_model_with_efficiency(
    *,
    task: LocalModelTask,
    deployments: tuple[LocalModelDeployment, ...],
    catalog: LocalModelCatalog,
    ledger: EngineEfficiencyLedgerSnapshot,
    tenant_id: str,
    as_of: datetime,
    policy: EngineEfficiencyRoutingPolicy | None = None,
) -> LocalModelSelection:
    """Use telemetry only to break ties inside the canonical quality/preference tier."""

    rules = policy or EngineEfficiencyRoutingPolicy()
    base = select_local_model(task=task, deployments=deployments, catalog=catalog)
    if not base.local_execution_available:
        return base
    ledger = EngineEfficiencyLedgerSnapshot.model_validate(ledger.model_dump(mode="json"))
    if ledger.tenant_id != tenant_id:
        raise ValueError("engine_efficiency_ledger_tenant_mismatch")

    eligible: list[LocalModelDeployment] = []
    for deployment in deployments:
        singleton = select_local_model(
            task=task,
            deployments=(deployment,),
            catalog=catalog,
        )
        if singleton.local_execution_available:
            eligible.append(deployment)
    if len(eligible) < 2:
        return base

    preferred_tier = max(
        1 if task.task_class in catalog.by_family()[item.model_family].preferred_tasks else 0
        for item in eligible
    )
    same_tier = [
        item
        for item in eligible
        if (
            1
            if task.task_class in catalog.by_family()[item.model_family].preferred_tasks
            else 0
        )
        == preferred_tier
    ]
    if len(same_tier) < 2:
        return base

    best_benchmark = max(item.benchmark_score or 0.0 for item in same_tier)
    quality_band = tuple(
        item
        for item in same_tier
        if (item.benchmark_score or 0.0) >= best_benchmark - rules.max_benchmark_delta
    )
    if len(quality_band) < 2:
        return base

    preferences = build_engine_efficiency_preferences(
        ledger=ledger,
        tenant_id=tenant_id,
        task_class=task.task_class,
        engine_ids=tuple(item.deployment_id for item in quality_band),
        as_of=as_of,
        min_samples=rules.min_samples_per_candidate,
    )
    preference_map = {item.engine_id: item for item in preferences}
    if rules.require_complete_quality_band and any(
        not preference_map[item.deployment_id].enough_samples for item in quality_band
    ):
        return base
    observed_candidates = [
        item
        for item in quality_band
        if preference_map[item.deployment_id].enough_samples
    ]
    if len(observed_candidates) < 2:
        return base

    def ranking(deployment: LocalModelDeployment) -> tuple[int, int, int, float, str]:
        preference = preference_map[deployment.deployment_id]
        average_cost = preference.average_provider_cost_microunits or 0
        latency = preference.p50_latency_ms or 0
        return (
            preference.success_rate_basis_points,
            -average_cost,
            -latency,
            deployment.benchmark_score or 0.0,
            deployment.deployment_id,
        )

    selected = max(observed_candidates, key=ranking)
    return LocalModelSelection(
        task_ref=task.task_ref,
        deployment_id=selected.deployment_id,
        model_family=selected.model_family,
        model_id=selected.model_id,
        benchmark_score=selected.benchmark_score,
        local_execution_available=True,
        paid_frontier_escalation_required=False,
    )
