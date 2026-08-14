from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_query_contract_policy import get_ai_query_contract_policy
from app.core.ai_tool_authorization import (
    AiToolAuthorizationError,
    AiToolName,
    derive_ai_tool_capability,
)
from app.core.authorization import require_permission
from app.core.permission_catalog import (
    ACTIONS,
    FEATURES,
    action_permission,
    feature_permission,
    module_permission,
)
from app.core.security import Principal

router = APIRouter(tags=["intelligence"])

JarvisViewer = Annotated[
    Principal,
    Depends(require_permission(module_permission("jarvis"))),
]
InsightViewer = Annotated[
    Principal,
    Depends(require_permission(module_permission("insight"))),
]
PlanogramViewer = Annotated[
    Principal,
    Depends(require_permission(module_permission("planogram"))),
]

_TOOLS: tuple[AiToolName, ...] = (
    "ops_kpi_query",
    "catalog_query",
    "regulatory_impact_query",
)

_PLANOGRAM_PHYSICAL_TRUTH_REQUIREMENTS = (
    "approved_sku_dimensions",
    "product_image_linkage",
    "store_dna",
    "fixture_geometry_capacity",
    "physical_layout_aisle",
    "pallet_fixture_authority",
)


def _granted_features(principal: Principal, module: str) -> list[str]:
    return sorted(
        feature
        for feature in FEATURES.get(module, ())
        if feature_permission(module, feature) in principal.permissions
    )


def _granted_actions(principal: Principal, module: str) -> list[str]:
    return sorted(
        action
        for action in ACTIONS.get(module, ())
        if action_permission(module, action) in principal.permissions
    )


def _tool_state(principal: Principal, tool: AiToolName) -> dict[str, object]:
    try:
        capability = derive_ai_tool_capability(principal, tool=tool)
    except AiToolAuthorizationError:
        capability = None

    if tool == "ops_kpi_query":
        candidate = ORDERS_V2_CANDIDATE
        production_ready = (
            not candidate.blockers
            and candidate.schema_evidence_fingerprint is not None
            and candidate.array_parameter_adapter_fingerprint is not None
            and candidate.cross_tenant_proof_fingerprint is not None
        )
        return {
            "tool": tool,
            "grant_eligible": capability is not None,
            "runtime_ready": production_ready,
            "query_contract_id": candidate.query_id,
            "activation_state": "ready" if production_ready else "blocked",
            "blockers": list(candidate.blockers),
            "data_scope_fingerprint": (
                capability.data_scope_fingerprint if capability else None
            ),
        }

    policy = get_ai_query_contract_policy(tool)
    return {
        "tool": tool,
        "grant_eligible": capability is not None,
        "runtime_ready": policy.production_ready,
        "query_contract_id": policy.contract_id,
        "activation_state": "ready" if policy.production_ready else "blocked",
        "blockers": list(policy.blockers),
        "data_scope_fingerprint": (
            capability.data_scope_fingerprint if capability else None
        ),
    }


def build_jarvis_workspace(principal: Principal) -> dict[str, object]:
    """Build a tenant-bound Jarvis product read model without issuing grants."""

    return {
        "tenant_id": str(principal.tenant_id),
        "actor": principal.subject,
        "features": _granted_features(principal, "jarvis"),
        "actions": _granted_actions(principal, "jarvis"),
        "tools": [_tool_state(principal, tool) for tool in _TOOLS],
        "security_guardian_visible": False,
    }


def build_insight_metrics(principal: Principal) -> dict[str, object]:
    """Expose canonical KPI readiness without duplicating metric SQL in UI."""

    candidate = ORDERS_V2_CANDIDATE
    production_ready = (
        not candidate.blockers
        and candidate.schema_evidence_fingerprint is not None
        and candidate.array_parameter_adapter_fingerprint is not None
        and candidate.cross_tenant_proof_fingerprint is not None
    )

    return {
        "tenant_id": str(principal.tenant_id),
        "actor": principal.subject,
        "features": _granted_features(principal, "insight"),
        "actions": _granted_actions(principal, "insight"),
        "metrics": [
            {
                "metric_id": candidate.query_id,
                "source": candidate.source_table,
                "production_ready": production_ready,
                "activation_state": "ready" if production_ready else "candidate",
                "tenant_discriminator": {
                    "expression": candidate.tenant_discriminator_expression,
                    "authority": "candidate_unverified",
                },
                "evidence": {
                    "schema": candidate.schema_evidence_fingerprint is not None,
                    "array_parameter_adapter": (
                        candidate.array_parameter_adapter_fingerprint is not None
                    ),
                    "cross_tenant_proof": (
                        candidate.cross_tenant_proof_fingerprint is not None
                    ),
                },
                "blockers": list(candidate.blockers),
            }
        ],
    }


def build_planogram_readiness(principal: Principal) -> dict[str, object]:
    """Expose the Core-authoritative Planogram gate without inventing physical evidence."""

    return {
        "tenant_id": str(principal.tenant_id),
        "actor": principal.subject,
        "authority": "eay_core_api",
        "features": _granted_features(principal, "planogram"),
        "actions": _granted_actions(principal, "planogram"),
        "engine": {
            "contract": "deterministic-physical-truth",
            "runtime_mode": "domain_library",
            "legacy_bridge_enabled": False,
            "parallel_planai_auth_allowed": False,
        },
        "physical_truth": {
            "evidence_state": "external_required",
            "verified_attestation": None,
            "required_evidence": list(_PLANOGRAM_PHYSICAL_TRUTH_REQUIREMENTS),
        },
        "solver_optimizer_allowed": False,
        "production_ready": False,
        "generation_state": "blocked_external_physical_truth",
    }


@router.get("/v1/jarvis/workspace")
async def get_jarvis_workspace(principal: JarvisViewer) -> dict[str, object]:
    return build_jarvis_workspace(principal)


@router.get("/v1/insight/metrics")
async def get_insight_metrics(principal: InsightViewer) -> dict[str, object]:
    return build_insight_metrics(principal)


@router.get("/v1/planogram/readiness", tags=["planogram"])
async def get_planogram_readiness(principal: PlanogramViewer) -> dict[str, object]:
    return build_planogram_readiness(principal)
