from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.ai.schema_attestation import (
    REQUIRED_ORDERS_V2_FIELDS,
    resolve_orders_v2_schema_attestation,
)
from app.ai.tool_grants import get_tool_contract
from app.core.permission_catalog import action_permission
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


def _orders_v2_attestation() -> Any:
    return resolve_orders_v2_schema_attestation(
        expected_table="curated_data_shared.orders",
        required_fields=REQUIRED_ORDERS_V2_FIELDS,
        scope_field="entity.id",
    )


def _orders_v2_blockers(principal: Principal) -> tuple[list[str], dict[str, Any]]:
    permission = action_permission("ai_assistant", "executeOpsRead")
    scope = _permission_scope(principal, permission)
    blockers: list[str] = []

    if permission not in principal.permissions:
        blockers.append("ops_read_permission_missing")
    if scope is None:
        blockers.append("server_authoritative_data_scope_missing")

    attestation = _orders_v2_attestation()
    if attestation is None:
        blockers.extend(
            [
                "authorized_read_only_bigquery_identity_missing",
                "live_schema_attestation_missing",
                "tenant_discriminator_unverified",
                "live_cross_tenant_zero_leak_proof_missing",
            ]
        )
        evidence = {
            "schema_attested": False,
            "tenant_discriminator_verified": False,
            "cross_tenant_proof_verified": False,
        }
    else:
        if not attestation.schema_evidence.verified:
            blockers.append("live_schema_attestation_unverified")
        if not attestation.scope_verified:
            blockers.append("tenant_discriminator_unverified")
        if not attestation.cross_tenant_proof_verified:
            blockers.append("live_cross_tenant_zero_leak_proof_missing")
        evidence = {
            "schema_attested": bool(attestation.schema_evidence.verified),
            "tenant_discriminator_verified": bool(attestation.scope_verified),
            "cross_tenant_proof_verified": bool(attestation.cross_tenant_proof_verified),
        }
    return blockers, evidence


def build_jarvis_workspace(principal: Principal) -> dict[str, Any]:
    blockers, evidence = _orders_v2_blockers(principal)
    tools: list[dict[str, Any]] = []

    for capability in ("ops_kpi_query", "app_read_query"):
        contract = get_tool_contract(capability)
        permission = action_permission("ai_assistant", contract.action)
        scope = _permission_scope(principal, permission)
        item: dict[str, Any] = {
            "tool": capability,
            "action": contract.action,
            "required_permission": permission,
            "grant_eligible": permission in principal.permissions,
            "scope_source": "server_authoritative_permission_assignment",
            "scope_available": scope is not None,
        }
        if capability == "ops_kpi_query":
            item.update(
                {
                    "query_contract_id": "ops.kpi.orders.v2",
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
    permission = action_permission("ai_assistant", "executeOpsRead")
    return {
        "tenant_id": str(principal.tenant_id),
        "authority": "canonical_metric_contracts",
        "frontend_metric_truth_allowed": False,
        "metrics": [
            {
                "metric_id": "ops.kpi.orders.v2",
                "family": "orders",
                "source_relation": "curated_data_shared.orders",
                "tenant_discriminator": {
                    "expression": "entity.id",
                    "authority": "candidate_unverified",
                },
                "required_permission": permission,
                "scope_source": "server_authoritative_permission_assignment",
                "activation_state": "candidate" if blockers else "ready_for_governed_activation",
                "production_ready": False,
                "evidence": {
                    "schema": evidence["schema_attested"],
                    "array_parameter_adapter": False,
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


@router.get("/planogram/readiness")
async def get_planogram_readiness(principal: Authenticated) -> dict[str, Any]:
    return build_planogram_readiness(principal)


@router.get("/platform/security-guardian/workspace")
async def get_security_guardian_workspace(principal: PlatformAdmin) -> dict[str, Any]:
    return build_security_guardian_workspace(principal)
