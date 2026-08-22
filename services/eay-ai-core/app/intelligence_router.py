"""Task-fit routing across local and frontier intelligence engines.

This module does not call any model provider. It produces an auditable routing
plan from registered, verified engines while preserving the EAY privacy and
safety boundary. Model quality must be supported by benchmark evidence;
confidential or restricted company data must never silently leave the local
boundary without explicit external-processing authorization.

For certification-required tasks, the canonical router also fails closed unless
the runtime supplies a fresh capability-admission set plus its sealed receipt
reference. This prevents benchmark/certificate authorities from becoming
advisory-only metadata that production routing can silently bypass.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .frontier3_certification_intelligence import FrontierCertificationDomain

INTELLIGENCE_ROUTER_CONTRACT = "eay-intelligence-router-v1"


class PrivacyLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class TaskComplexity(str, Enum):
    ROUTINE = "routine"
    STANDARD = "standard"
    HARD = "hard"
    EXTREME = "extreme"


class TaskRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN = "screen"
    CODE = "code"


class EngineClass(str, Enum):
    LOCAL = "local"
    FRONTIER = "frontier"
    SPECIALIST = "specialist"


_PRIVACY_ORDER = {
    PrivacyLevel.PUBLIC: 0,
    PrivacyLevel.INTERNAL: 1,
    PrivacyLevel.CONFIDENTIAL: 2,
    PrivacyLevel.RESTRICTED: 3,
}

_RISK_ORDER = {
    TaskRisk.LOW: 0,
    TaskRisk.MEDIUM: 1,
    TaskRisk.HIGH: 2,
    TaskRisk.CRITICAL: 3,
}


class IntelligenceEngine(BaseModel):
    engine_id: str = Field(min_length=1)
    engine_class: EngineClass
    modalities: tuple[Modality, ...] = (Modality.TEXT,)
    supports_tools: bool = False
    supports_long_horizon: bool = False
    supports_parallel_delegation: bool = False
    local_processing: bool = False
    maximum_privacy: PrivacyLevel = PrivacyLevel.PUBLIC
    maximum_risk: TaskRisk = TaskRisk.LOW
    exact_adapter_verified: bool = False
    production_enabled: bool = False
    benchmark_score: float | None = Field(default=None, ge=0.0, le=1.0)
    benchmark_evidence_ref: str | None = None
    independent_provider_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def benchmark_claim_requires_evidence(self) -> "IntelligenceEngine":
        if self.benchmark_score is not None and not self.benchmark_evidence_ref:
            raise ValueError("engine_benchmark_score_requires_evidence")
        if self.engine_class is EngineClass.LOCAL and not self.local_processing:
            raise ValueError("local_engine_must_process_locally")
        return self


class IntelligenceTask(BaseModel):
    task_id: str = Field(min_length=1)
    complexity: TaskComplexity
    risk: TaskRisk
    privacy: PrivacyLevel
    modalities: tuple[Modality, ...] = (Modality.TEXT,)
    requires_tools: bool = False
    requires_long_horizon: bool = False
    external_processing_authorized: bool = False
    requires_independent_critique: bool = False
    certification_domain: FrontierCertificationDomain | None = None
    requires_fresh_certification: bool = False

    @model_validator(mode="after")
    def certification_requirement_is_explicit(self) -> "IntelligenceTask":
        if self.requires_fresh_certification and self.certification_domain is None:
            raise ValueError(
                "fresh_certification_task_requires_certification_domain"
            )
        return self


class IntelligenceRoutingPlan(BaseModel):
    contract: str = INTELLIGENCE_ROUTER_CONTRACT
    task_id: str
    primary_engine_id: str | None = None
    critic_engine_ids: tuple[str, ...] = ()
    council_required: bool = False
    execution_permitted: bool = False
    blockers: tuple[str, ...] = ()
    certification_admission_ref: str | None = None
    external_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def blocked_plan_cannot_execute(self) -> "IntelligenceRoutingPlan":
        if self.execution_permitted and self.blockers:
            raise ValueError("intelligence_routing_cannot_ignore_blockers")
        if self.external_side_effects_authorized:
            raise ValueError("intelligence_router_never_authorizes_side_effects")
        return self


def engine_satisfies_task_boundary(
    task: IntelligenceTask,
    engine: IntelligenceEngine,
    *,
    require_production_enabled: bool = True,
) -> bool:
    """Return whether one engine satisfies task privacy/risk/modality boundaries.

    Benchmark-only callers may set ``require_production_enabled=False`` to
    evaluate an exact-adapter-verified candidate before promotion. All other
    privacy, risk, modality, tool and external-processing constraints remain
    identical to normal routing.
    """

    if require_production_enabled and not engine.production_enabled:
        return False
    if not engine.exact_adapter_verified:
        return False
    if _PRIVACY_ORDER[task.privacy] > _PRIVACY_ORDER[engine.maximum_privacy]:
        return False
    if _RISK_ORDER[task.risk] > _RISK_ORDER[engine.maximum_risk]:
        return False
    if any(modality not in engine.modalities for modality in task.modalities):
        return False
    if task.requires_tools and not engine.supports_tools:
        return False
    if task.requires_long_horizon and not engine.supports_long_horizon:
        return False
    if (
        task.privacy in {PrivacyLevel.CONFIDENTIAL, PrivacyLevel.RESTRICTED}
        and not engine.local_processing
        and not task.external_processing_authorized
    ):
        return False
    return True


def _engine_is_eligible(task: IntelligenceTask, engine: IntelligenceEngine) -> bool:
    return engine_satisfies_task_boundary(
        task, engine, require_production_enabled=True
    )


def _score_engine(
    task: IntelligenceTask, engine: IntelligenceEngine
) -> tuple[float, str]:
    """Use evidence-backed quality as one signal, never as an unverified claim."""

    score = engine.benchmark_score if engine.benchmark_score is not None else 0.50
    if engine.local_processing and task.privacy in {
        PrivacyLevel.CONFIDENTIAL,
        PrivacyLevel.RESTRICTED,
    }:
        score += 0.12
    if (
        engine.supports_parallel_delegation
        and task.complexity is TaskComplexity.EXTREME
    ):
        score += 0.08
    if engine.supports_long_horizon and task.requires_long_horizon:
        score += 0.08
    if engine.engine_class is EngineClass.SPECIALIST and len(task.modalities) > 1:
        score += 0.04
    return (min(score, 1.0), engine.engine_id)


def route_intelligence(
    task: IntelligenceTask,
    engines: list[IntelligenceEngine],
    *,
    certified_engine_ids: set[str] | frozenset[str] | None = None,
    certification_admission_ref: str | None = None,
) -> IntelligenceRoutingPlan:
    """Build one canonical route, optionally enforcing fresh certificate admission.

    When ``task.requires_fresh_certification`` is true, ordinary
    ``production_enabled`` and historical ``benchmark_score`` metadata is
    insufficient. The composition root must supply the exact currently admitted
    engine IDs and a sealed admission receipt reference. Missing admission fails
    closed before any provider or tool invocation can occur.
    """

    if task.requires_fresh_certification:
        if certified_engine_ids is None or not certification_admission_ref:
            return IntelligenceRoutingPlan(
                task_id=task.task_id,
                blockers=("fresh_capability_certification_admission_missing",),
            )
        eligible = [
            engine
            for engine in engines
            if engine.engine_id in certified_engine_ids
            and _engine_is_eligible(task, engine)
        ]
        if not eligible:
            return IntelligenceRoutingPlan(
                task_id=task.task_id,
                blockers=(
                    "no_fresh_certified_engine_satisfies_task_boundary",
                ),
                certification_admission_ref=certification_admission_ref,
            )
    else:
        eligible = [
            engine for engine in engines if _engine_is_eligible(task, engine)
        ]

    if not eligible:
        return IntelligenceRoutingPlan(
            task_id=task.task_id,
            blockers=("no_verified_engine_satisfies_task_boundary",),
        )

    ranked = sorted(
        eligible,
        key=lambda engine: _score_engine(task, engine),
        reverse=True,
    )
    primary = ranked[0]

    council_required = (
        task.complexity is TaskComplexity.EXTREME
        or task.risk is TaskRisk.CRITICAL
    )
    critique_required = (
        task.requires_independent_critique
        or task.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL}
    )
    critic_ids: list[str] = []

    if critique_required:
        for candidate in ranked[1:]:
            if (
                candidate.independent_provider_key
                == primary.independent_provider_key
            ):
                continue
            critic_ids.append(candidate.engine_id)
            if not council_required or len(critic_ids) >= 2:
                break

    blockers: list[str] = []
    if critique_required and not critic_ids:
        blockers.append("independent_critic_unavailable")
    selected_provider_keys = {primary.independent_provider_key}
    selected_provider_keys.update(
        e.independent_provider_key
        for e in ranked
        if e.engine_id in critic_ids
    )
    if council_required and len(selected_provider_keys) < 2:
        blockers.append("council_provider_diversity_insufficient")

    return IntelligenceRoutingPlan(
        task_id=task.task_id,
        primary_engine_id=primary.engine_id,
        critic_engine_ids=tuple(critic_ids),
        council_required=council_required,
        execution_permitted=not blockers,
        blockers=tuple(blockers),
        certification_admission_ref=(
            certification_admission_ref
            if task.requires_fresh_certification
            else None
        ),
    )
