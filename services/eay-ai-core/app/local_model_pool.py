"""Governed local/open-model pool for Jarvis.

Jarvis is local-first. Open-weight/local models are treated as task specialists,
not as an undifferentiated fallback. A model may participate only when its
license posture, runtime availability, benchmark evidence, language support and
task capability are explicit. No catalog entry makes a model production-active
by itself.

Paid frontier escalation is outside this module and remains platform-admin
controlled by paid-token governance.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field, model_validator

LOCAL_MODEL_POOL_CONTRACT = "eay-local-model-pool-v1"


class LocalCapability(str, Enum):
    TEXT = "TEXT"
    CODE = "CODE"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    ASR = "ASR"
    TTS = "TTS"
    REASONING = "REASONING"
    TOOL_PLANNING = "TOOL_PLANNING"
    AGENTIC = "AGENTIC"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    MULTILINGUAL = "MULTILINGUAL"
    RETRIEVAL_SYNTHESIS = "RETRIEVAL_SYNTHESIS"
    OPS_REASONING = "OPS_REASONING"


class CommercialUseStatus(str, Enum):
    INTERNAL_APPROVED = "INTERNAL_APPROVED"
    PERMISSIVE_LICENSE_REVIEWED = "PERMISSIVE_LICENSE_REVIEWED"
    PERMISSIVE_LICENSE_REVIEWED_WITH_USAGE_POLICY = "PERMISSIVE_LICENSE_REVIEWED_WITH_USAGE_POLICY"
    CONDITIONAL_LEGAL_REVIEW_REQUIRED = "CONDITIONAL_LEGAL_REVIEW_REQUIRED"
    VERSION_SPECIFIC_LICENSE_REVIEW_REQUIRED = "VERSION_SPECIFIC_LICENSE_REVIEW_REQUIRED"


class LocalModelCatalogEntry(BaseModel):
    model_family: str = Field(min_length=1)
    recommended_runtime: str = Field(min_length=1)
    default_model_id: str | None = None
    license: str = Field(min_length=1)
    commercial_use_status: CommercialUseStatus
    capabilities: frozenset[LocalCapability]
    preferred_tasks: frozenset[str]
    supported_languages: frozenset[str] = frozenset()
    production_candidate: bool
    external_network_required: bool = False

    @model_validator(mode="after")
    def production_candidate_requires_reviewed_commercial_posture(self) -> "LocalModelCatalogEntry":
        reviewed = {
            CommercialUseStatus.INTERNAL_APPROVED,
            CommercialUseStatus.PERMISSIVE_LICENSE_REVIEWED,
            CommercialUseStatus.PERMISSIVE_LICENSE_REVIEWED_WITH_USAGE_POLICY,
        }
        if self.production_candidate and self.commercial_use_status not in reviewed:
            raise ValueError("local_model_production_candidate_requires_reviewed_commercial_posture")
        if self.external_network_required:
            raise ValueError("local_model_pool_cannot_require_external_network")
        normalized = [item.casefold() for item in self.supported_languages]
        if len(normalized) != len(set(normalized)):
            raise ValueError("local_model_supported_languages_duplicate")
        return self


class LocalModelDeployment(BaseModel):
    deployment_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    enabled: bool = False
    runtime_reachable: bool = False
    benchmark_score: float | None = Field(default=None, ge=0.0, le=1.0)
    benchmark_evidence_ref: str | None = None
    observed_capabilities: frozenset[LocalCapability] = frozenset()
    max_context_tokens: int | None = Field(default=None, gt=0)
    hardware_profile_ref: str | None = None

    @model_validator(mode="after")
    def active_deployment_requires_evidence(self) -> "LocalModelDeployment":
        if self.enabled:
            if not self.runtime_reachable:
                raise ValueError("local_model_enabled_deployment_requires_reachable_runtime")
            if self.benchmark_score is None or not self.benchmark_evidence_ref:
                raise ValueError("local_model_enabled_deployment_requires_benchmark_evidence")
            if not self.observed_capabilities:
                raise ValueError("local_model_enabled_deployment_requires_observed_capabilities")
        return self


class LocalModelTask(BaseModel):
    task_ref: str = Field(min_length=1)
    task_class: str = Field(min_length=1)
    required_capabilities: frozenset[LocalCapability]
    minimum_benchmark_score: float = Field(default=0.0, ge=0.0, le=1.0)
    minimum_context_tokens: int | None = Field(default=None, gt=0)
    language_code: str | None = Field(default=None, min_length=2, max_length=16)

    @model_validator(mode="after")
    def language_is_normalized(self) -> "LocalModelTask":
        if self.language_code is not None:
            normalized = self.language_code.strip().casefold()
            if normalized != self.language_code:
                raise ValueError("local_model_task_language_code_must_be_lowercase")
        return self


class LocalModelSelection(BaseModel):
    contract: str = LOCAL_MODEL_POOL_CONTRACT
    task_ref: str
    deployment_id: str | None = None
    model_family: str | None = None
    model_id: str | None = None
    benchmark_score: float | None = None
    local_execution_available: bool = False
    paid_frontier_escalation_required: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def selection_is_consistent(self) -> "LocalModelSelection":
        selected = self.deployment_id is not None
        if selected != self.local_execution_available:
            raise ValueError("local_model_selection_state_mismatch")
        if selected and self.paid_frontier_escalation_required:
            raise ValueError("local_model_selection_cannot_require_paid_escalation_when_selected")
        if not selected and not self.paid_frontier_escalation_required:
            raise ValueError("local_model_selection_missing_escalation_state")
        return self


class LocalModelCatalog(BaseModel):
    version: int = Field(ge=1)
    models: tuple[LocalModelCatalogEntry, ...]

    @model_validator(mode="after")
    def catalog_has_unique_families(self) -> "LocalModelCatalog":
        families = [item.model_family for item in self.models]
        if len(families) != len(set(families)):
            raise ValueError("local_model_catalog_duplicate_family")
        return self

    def by_family(self) -> dict[str, LocalModelCatalogEntry]:
        return {item.model_family: item for item in self.models}


def load_local_model_catalog(path: str | Path) -> LocalModelCatalog:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LocalModelCatalog.model_validate(payload)


def _eligible(
    *,
    task: LocalModelTask,
    deployment: LocalModelDeployment,
    catalog: LocalModelCatalog,
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    entry = catalog.by_family().get(deployment.model_family)
    if entry is None:
        blockers.append("local_model_family_not_in_catalog")
        return False, tuple(blockers)
    if not entry.production_candidate:
        blockers.append("local_model_family_not_production_candidate")
    if not deployment.enabled or not deployment.runtime_reachable:
        blockers.append("local_model_deployment_not_active")
    if deployment.benchmark_score is None or not deployment.benchmark_evidence_ref:
        blockers.append("local_model_benchmark_evidence_missing")
    elif deployment.benchmark_score < task.minimum_benchmark_score:
        blockers.append("local_model_benchmark_below_task_floor")
    if not task.required_capabilities.issubset(entry.capabilities):
        blockers.append("local_model_catalog_capability_missing")
    if not task.required_capabilities.issubset(deployment.observed_capabilities):
        blockers.append("local_model_observed_capability_missing")
    if task.language_code is not None:
        supported = {item.casefold() for item in entry.supported_languages}
        if task.language_code not in supported:
            blockers.append("local_model_language_support_not_verified")
    if task.minimum_context_tokens is not None:
        if deployment.max_context_tokens is None or deployment.max_context_tokens < task.minimum_context_tokens:
            blockers.append("local_model_context_window_insufficient")
    return not blockers, tuple(blockers)


def select_local_model(
    *,
    task: LocalModelTask,
    deployments: Iterable[LocalModelDeployment],
    catalog: LocalModelCatalog,
) -> LocalModelSelection:
    eligible: list[tuple[float, int, LocalModelDeployment]] = []
    seen_blockers: list[str] = []
    for deployment in deployments:
        ok, blockers = _eligible(task=task, deployment=deployment, catalog=catalog)
        seen_blockers.extend(blockers)
        if not ok:
            continue
        entry = catalog.by_family()[deployment.model_family]
        preferred = 1 if task.task_class in entry.preferred_tasks else 0
        eligible.append((deployment.benchmark_score or 0.0, preferred, deployment))

    if not eligible:
        return LocalModelSelection(
            task_ref=task.task_ref,
            local_execution_available=False,
            paid_frontier_escalation_required=True,
            blockers=tuple(dict.fromkeys(seen_blockers)) or ("local_model_candidate_missing",),
        )

    _, _, selected = max(eligible, key=lambda item: (item[1], item[0], item[2].deployment_id))
    return LocalModelSelection(
        task_ref=task.task_ref,
        deployment_id=selected.deployment_id,
        model_family=selected.model_family,
        model_id=selected.model_id,
        benchmark_score=selected.benchmark_score,
        local_execution_available=True,
        paid_frontier_escalation_required=False,
    )
