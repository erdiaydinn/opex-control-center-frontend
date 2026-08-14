from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_tool_authorization import SCOPE_PERMISSION_KEYS, TOOL_REQUIRED_SCOPES
from app.core.security import Principal, get_current_principal, require_platform_admin

router = APIRouter(prefix="/v1", tags=["intelligence"])
Authenticated = Annotated[Principal, Depends(get_current_principal)]
PlatformAdmin = Annotated[Principal, Depends(require_platform_admin)]

PLANOGRAM_REQUIRED_EVIDENCE = (
    "approved_sku_dimensions",
    "product_image_linkage",
    "store_dna",
    "fixture_geometry_capacity",
    "physical_layout_aisle",
    "pallet_fixture_authority",
)

SECURITY_GUARDIAN_THREAT_SOURCES = (
    "cisa_kev",
    "osv",
    "github_advisory",
)


def _permission_scope(principal: Principal, permission: str) -> dict[str, object] | None:
    for assignment in principal.permission_assignments:
        if assignment.key == permission:
            return dict(assignment.scope)
    return None


def _single_scope_tool_permission(tool: str) -> str:
    scopes = TOOL_REQUIRED_SCOPES.get(tool)
    if not scopes or len(scopes) != 1:
        raise RuntimeError(f"Unsupported intelligence workspace tool contract: {tool}")
    return SCOPE_PERMISSION_KEYS[scopes[0]]


def _orders_v2_blockers(principal: Principal) -> tuple[list[str], dict[str, bool]]:
    permission = _single_scope_tool_permission("ops_kpi_query")
    scope = _permission_scope(principal, permission)
    candidate = ORDERS_V2_CANDIDATE

    blockers: list[str] = []
    if permission not in principal.permissions:
        blockers.append("ops_read_permission_missing")
    if scope is None:
        blockers.append("server_authoritative_data_scope_missing")

    # The version-controlled candidate is intentionally the authority for
    # readiness here. There is no separate runtime attestation registry in
    # Core API today, so a UI/workspace must not infer live evidence from a
    # caller payload or from a synthetic test artifact.
    blockers.extend(candidate.blockers)
    if candidate.schema_evidence_fingerprint is None:
        blockers.extend(
            (
                "authorized_read_only_bigquery_identity_missing",
                "live_schema_attestation_missing",
                "tenant_discriminator_unverified",
            )
        )
    if candidate.array_parameter_adapter_fingerprint is None:
        blockers.append("bigquery_array_parameter_adapter_unverified")
    if candidate.cross_tenant_proof_fingerprint is None:
        blockers.append("live_cross_tenant_zero_leak_proof_missing")

    # Stable order without silently dropping duplicate evidence reasons.
    blockers = list(dict.fromkeys(blockers))
    evidence = {
        "schema_attested": candidate.schema_evidence_fingerprint is not None,
        "tenant_discriminator_verified": candidate.schema_evidence_fingerprint is not None,
        "array_parameter_adapter_verified": (
            candidate.array_parameter_adapter_fingerprint is not None
        ),
        "cross_tenant_proof_verified": candidate.cross_tenant_proof_fingerprint is not None,
    }
    return blockers, evidence


def build_jarvis_workspace(principal: Principal) -> dict[str, Any]:
    blockers, evidence = _orders_v2_blockers(principal)
    tools: list[dict[str, Any]] = []

    for capability in ("ops_kpi_query", "catalog_query"):
        permission = _single_scope_tool_permission(capability)
        scope = _permission_scope(principal, permission)
        item: dict[str, Any] = {
            "tool": capability,
            "action": permission.rsplit(":", 1)[-1],
            "required_permission": permission,
            "grant_eligible": permission in principal.permissions,
            "scope_source": "server_authoritative_permission_assignment",
            "scope_available": scope is not None,
        }
        if capability == "ops_kpi_query":
            item.update(
                {
                    "query_contract_id": ORDERS_V2_CANDIDATE.query_id,
                    "runtime_ready": len(blockers) == 0,
                    "activation_state": "ready" if len(blockers) == 0 else "blocked",
                    "blockers": blockers,
                    "evidence": evidence,
                }
            )
        tools.append(item)

    return {
        "tenant_id": str(principal.tenant_id),
        "actor": principal.subject,
        "authority": "eay_core_api",
        "security_guardian_visible": False,
        "security_guardian_scope": "platform_admin_only",
        "tools": tools,
        "production_ready": False,
    }


def build_insight_metrics(principal: Principal) -> dict[str, Any]:
    blockers, evidence = _orders_v2_blockers(principal)
    permission = _single_scope_tool_permission("ops_kpi_query")
    candidate = ORDERS_V2_CANDIDATE
    return {
        "tenant_id": str(principal.tenant_id),
        "authority": "canonical_metric_contracts",
        "frontend_metric_truth_allowed": False,
        "metrics": [
            {
                "metric_id": candidate.query_id,
                "family": "orders",
                "source_relation": candidate.source_table,
                "tenant_discriminator": {
                    "expression": candidate.tenant_discriminator_expression,
                    "authority": "candidate_unverified",
                },
                "required_permission": permission,
                "scope_source": "server_authoritative_permission_assignment",
                "activation_state": "candidate" if blockers else "ready_for_governed_activation",
                "production_ready": False,
                "evidence": {
                    "schema": evidence["schema_attested"],
                    "array_parameter_adapter": evidence["array_parameter_adapter_verified"],
                    "cross_tenant_proof": evidence["cross_tenant_proof_verified"],
                },
                "blockers": blockers,
            }
        ],
    }


def build_planogram_readiness(principal: Principal) -> dict[str, Any]:
    return {
        "tenant_id": str(principal.tenant_id),
        "authority": "eay_core_api",
        "engine": {
            "contract": "deterministic-physical-truth",
            "runtime_mode": "domain_library",
            "legacy_bridge_enabled": False,
            "parallel_planai_auth_allowed": False,
        },
        "physical_truth": {
            "evidence_state": "external_required",
            "verified_attestation": None,
            "required_evidence": list(PLANOGRAM_REQUIRED_EVIDENCE),
        },
        "solver_optimizer_allowed": False,
        "production_ready": False,
    }


def build_security_guardian_workspace(_: Principal) -> dict[str, Any]:
    return {
        "scope": "eay_platform",
        "visibility": "platform_admin_only",
        "mode": "read_only_assessment",
        "production_ready": False,
        "security_posture": "not_scored_without_observation_evidence",
        "last_observed_at": None,
        "findings": {
            "state": "unknown_without_observation_evidence",
            "counts": {
                "critical": None,
                "high": None,
                "medium": None,
                "low": None,
            },
            "items": [],
        },
        "threat_intelligence": [
            {
                "source_id": source_id,
                "integration_state": "not_connected",
                "last_observed_at": None,
            }
            for source_id in SECURITY_GUARDIAN_THREAT_SOURCES
        ],
        "controls": [
            {
                "control_id": "tenant_authority",
                "implementation_state": "implemented",
                "evidence_state": "repository_and_ci",
            },
            {
                "control_id": "platform_admin_scope",
                "implementation_state": "implemented",
                "evidence_state": "repository_and_ci",
            },
            {
                "control_id": "audit_boundary",
                "implementation_state": "implemented",
                "evidence_state": "repository_and_ci",
            },
            {
                "control_id": "approval_bound_remediation",
                "implementation_state": "existing_platform_authority_not_wired",
                "evidence_state": "integration_required",
            },
        ],
        "release_policy": {
            "customer_visibility": False,
            "automatic_production_remediation": False,
            "human_approval_required": True,
            "zero_findings_without_evidence_allowed": False,
        },
        "blockers": [
            "external_threat_intelligence_ingestion_missing",
            "dependency_sbom_inventory_missing",
            "reachable_code_analysis_missing",
            "deployment_inventory_observation_missing",
            "signed_finding_evidence_missing",
            "approval_bound_remediation_adapter_missing",
        ],
    }


@router.get("/jarvis/workspace")
async def get_jarvis_workspace(principal: Authenticated) -> dict[str, Any]:
    return build_jarvis_workspace(principal)


@router.get("/insight/metrics")
async def get_insight_metrics(principal: Authenticated) -> dict[str, Any]:
    return build_insight_metrics(principal)


@router.get("/platform/security-guardian/workspace")
async def get_security_guardian_workspace(principal: PlatformAdmin) -> dict[str, Any]:
    return build_security_guardian_workspace(principal)
