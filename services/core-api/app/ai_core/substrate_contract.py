"""Master 39 shared AI substrate contract without mutating frozen AI Core PR #15."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

FROZEN_AI_CORE_PR = 15
FROZEN_AI_CORE_HEAD = "9e1422df2a584b71593c2f6188d26c8ab4ab4c15"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_CAPABILITIES = frozenset(
    {
        "regulatory_ingestion_watch",
        "legal_temporal_resolution",
        "company_law_conflict",
        "grounded_rag",
        "local_model_router",
        "evaluation",
        "learning",
        "vision_provenance",
        "safety",
        "model_registry",
        "canary",
        "observability",
        "promotion_gate",
    }
)
REQUIRED_CONSUMERS = frozenset(
    {
        "jarvis",
        "insight",
        "field_intelligence",
        "workforce",
        "inventory",
        "planogram",
        "dockos",
        "budget",
        "academy",
        "audit",
    }
)


@dataclass(frozen=True)
class AiSubstrateContract:
    frozen_pr: int
    frozen_head_sha: str
    capabilities: frozenset[str]
    consumers: frozenset[str]
    source_provenance_required: bool
    tenant_authorization_required: bool
    promotion_requires_eval: bool
    promotion_requires_human_approval: bool


def _string_set(raw: object, *, field: str) -> frozenset[str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{field} must be a non-empty list")
    values = tuple(str(item).strip() for item in raw)
    if any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{field} contains empty or duplicate values")
    return frozenset(values)


def load_substrate_contract(path: Path) -> AiSubstrateContract:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported AI substrate schema")

    frozen = data.get("frozen_baseline")
    if not isinstance(frozen, dict):
        raise ValueError("AI Core frozen baseline is missing")
    head_sha = str(frozen.get("head_sha", "")).lower()
    if not SHA40.fullmatch(head_sha):
        raise ValueError("AI Core frozen head must be an exact commit SHA")
    if (
        frozen.get("pull_request") != FROZEN_AI_CORE_PR
        or head_sha != FROZEN_AI_CORE_HEAD
        or frozen.get("mutable") is not False
    ):
        raise ValueError("AI Core frozen PR #15 contract changed")

    capabilities = _string_set(data.get("capabilities"), field="capabilities")
    consumers = _string_set(data.get("consumer_modules"), field="consumer_modules")
    if not REQUIRED_CAPABILITIES.issubset(capabilities):
        raise ValueError("AI substrate dropped required frozen capabilities")
    if not REQUIRED_CONSUMERS.issubset(consumers):
        raise ValueError("AI substrate dropped required platform consumers")

    boundaries = data.get("truth_boundaries")
    if not isinstance(boundaries, dict):
        raise ValueError("AI substrate truth boundaries are missing")
    required_true = (
        "promotion_requires_eval",
        "promotion_requires_human_approval",
        "source_provenance_required",
        "tenant_authorization_required",
    )
    if not all(boundaries.get(key) is True for key in required_true):
        raise ValueError("AI Core promotion/source/tenant gate weakened")
    if (
        boundaries.get("self_modify_production_weights") is not False
        or boundaries.get("synthetic_is_production_evidence") is not False
    ):
        raise ValueError("AI Core production truth boundary weakened")

    return AiSubstrateContract(
        frozen_pr=FROZEN_AI_CORE_PR,
        frozen_head_sha=FROZEN_AI_CORE_HEAD,
        capabilities=capabilities,
        consumers=consumers,
        source_provenance_required=True,
        tenant_authorization_required=True,
        promotion_requires_eval=True,
        promotion_requires_human_approval=True,
    )


def authorize_consumer(
    contract: AiSubstrateContract,
    *,
    module: str,
    tenant_authorized: bool,
    provenance_bound: bool,
) -> bool:
    """Shared substrate is capability metadata, never a tenant authorization bypass."""

    normalized_module = module.strip()
    return (
        bool(normalized_module)
        and normalized_module in contract.consumers
        and tenant_authorized
        and provenance_bound
    )
