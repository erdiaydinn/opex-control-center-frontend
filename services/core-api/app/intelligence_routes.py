from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_tool_authorization import SCOPE_PERMISSION_KEYS, TOOL_REQUIRED_SCOPES
from app.core.authorization import require_control_plane_admin, require_permission
from app.core.security import Principal
from app.modules.field_intelligence.authorization import require_field_permission
from app.modules.field_intelligence.mobile_offline import (
    FieldOfflineSyncError,
    set_template_evidence_policy,
    sync_offline_batch,
)
from app.modules.field_intelligence.repository import (
    FieldRepositoryError,
    create_mission,
    create_template,
    field_analytics,
    get_mission_detail,
    list_evidence,
    list_locations,
    list_missions,
    list_templates,
    queue_notification_intents,
    review_evidence,
    set_mission_status,
    submit_evidence,
    upsert_location,
)
from app.modules.field_intelligence.schemas import (
    EvidencePolicy,
    EvidenceReview,
    EvidenceSubmit,
    LocationUpsert,
    MissionCreate,
    NotificationIntentCreate,
    OfflineSyncBatch,
    TemplateCreate,
)

router = APIRouter(prefix="/v1", tags=["intelligence"])

jarvis_view_guard = require_permission("module:jarvis:view")
insight_view_guard = require_permission("module:insight:view")
field_view_guard = require_permission("module:field_intelligence:view")
JarvisViewer = Annotated[Principal, Depends(jarvis_view_guard)]
InsightViewer = Annotated[Principal, Depends(insight_view_guard)]
FieldViewer = Annotated[Principal, Depends(field_view_guard)]
ControlPlaneAdmin = Annotated[Principal, Depends(require_control_plane_admin)]

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
                "control_id": "dependency_inventory",
                "implementation_state": "implemented_build_evidence",
                "evidence_state": "cyclonedx_prebuild_and_build_ci",
            },
            {
                "control_id": "approval_bound_remediation",
                "implementation_state": "existing_platform_authority_not_wired",
                "evidence_state": "integration_required",
            },
        ],
        "dependency_inventory": {
            "format": "CycloneDX",
            "spec_version": "1.7",
            "source_inventory": {
                "lifecycle": "pre-build",
                "npm_resolution": "lockfile_resolved",
                "python_resolution": "declared_direct",
            },
            "build_inventory": {
                "core_python": "resolved_installed_dependency_closure",
                "identity_python": "resolved_installed_dependency_closure",
                "android_release_runtime": "gradle_release_runtime_classpath_resolved",
            },
            "graph_semantics": "build_environment_conservative_not_reachability",
            "runtime_deployment_attested": False,
        },
        "release_policy": {
            "customer_visibility": False,
            "automatic_production_remediation": False,
            "human_approval_required": True,
            "zero_findings_without_evidence_allowed": False,
        },
        "blockers": [
            "external_threat_intelligence_ingestion_missing",
            "runtime_deployment_sbom_observation_missing",
            "reachable_code_analysis_missing",
            "deployment_inventory_observation_missing",
            "signed_finding_evidence_missing",
            "approval_bound_remediation_adapter_missing",
        ],
    }


@router.get("/jarvis/workspace")
async def get_jarvis_workspace(principal: JarvisViewer) -> dict[str, Any]:
    return build_jarvis_workspace(principal)


@router.get("/insight/metrics")
async def get_insight_metrics(principal: InsightViewer) -> dict[str, Any]:
    return build_insight_metrics(principal)


@router.get("/platform/security-guardian/workspace")
async def get_security_guardian_workspace(principal: ControlPlaneAdmin) -> dict[str, Any]:
    return build_security_guardian_workspace(principal)


def _field_bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _field_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Field resource not found in authorized scope",
    )


@router.get("/field/bootstrap")
async def field_bootstrap(principal: FieldViewer) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    tenant_id = str(principal.tenant_id)
    locations = await list_locations(tenant_id, scope)
    templates = await list_templates(tenant_id)
    missions = await list_missions(tenant_id, scope)
    return {
        "tenant_id": tenant_id,
        "scope": scope.model_dump(mode="json"),
        "locations": locations,
        "templates": templates,
        "missions": missions,
    }


@router.get("/field/missions")
async def field_missions(
    principal: FieldViewer,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    items = await list_missions(str(principal.tenant_id), scope, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/field/missions/{mission_id}")
async def field_mission_detail(
    mission_id: str,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    item = await get_mission_detail(str(principal.tenant_id), scope, mission_id)
    if item is None:
        raise _field_not_found()
    return item


@router.post("/field/missions", status_code=status.HTTP_201_CREATED)
async def post_field_mission(payload: MissionCreate, principal: FieldViewer) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:createMission")
    if payload.activate:
        require_field_permission(principal, "action:field_intelligence:activateMission")
    try:
        return await create_mission(str(principal.tenant_id), principal.subject, payload, scope)
    except FieldRepositoryError as exc:
        raise _field_bad_request(exc) from exc


@router.post("/field/missions/{mission_id}/activate")
async def activate_field_mission(
    mission_id: str,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:activateMission")
    try:
        return await set_mission_status(
            str(principal.tenant_id), scope, mission_id, transition="activate"
        )
    except FieldRepositoryError as exc:
        raise _field_bad_request(exc) from exc


@router.post("/field/missions/{mission_id}/cancel")
async def cancel_field_mission(
    mission_id: str,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:cancelMission")
    try:
        return await set_mission_status(
            str(principal.tenant_id), scope, mission_id, transition="cancel"
        )
    except FieldRepositoryError as exc:
        raise _field_bad_request(exc) from exc


@router.post(
    "/field/missions/{mission_id}/targets/{location_id}/evidence",
    status_code=status.HTTP_201_CREATED,
)
async def post_field_evidence(
    mission_id: str,
    location_id: str,
    payload: EvidenceSubmit,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:submitEvidence")
    try:
        return await submit_evidence(
            str(principal.tenant_id),
            principal.subject,
            scope,
            mission_id,
            location_id,
            payload,
        )
    except FieldRepositoryError as exc:
        raise _field_bad_request(exc) from exc


@router.post("/field/offline-sync")
async def post_field_offline_sync(
    payload: OfflineSyncBatch,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:submitEvidence")
    try:
        # Browser device_id/capture attributes are replay metadata only. Until
        # canonical App Attest/Play Integrity/camera attestation providers are
        # connected, policy-restricted evidence fails closed through empty
        # authoritative attestation sets.
        return await sync_offline_batch(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            scope=scope,
            batch=payload,
        )
    except FieldOfflineSyncError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/field/evidence")
async def field_evidence(
    principal: FieldViewer,
    mission_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:viewEvidence")
    items = await list_evidence(
        str(principal.tenant_id),
        scope,
        mission_id=mission_id,
        limit=limit,
    )
    return {"count": len(items), "items": items}


@router.post("/field/evidence/{evidence_id}/review")
async def post_field_evidence_review(
    evidence_id: str,
    payload: EvidenceReview,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:reviewEvidence")
    try:
        return await review_evidence(
            str(principal.tenant_id),
            principal.subject,
            scope,
            evidence_id,
            payload,
        )
    except FieldRepositoryError as exc:
        raise _field_bad_request(exc) from exc


@router.post(
    "/field/missions/{mission_id}/notification-intents",
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_field_notification_intents(
    mission_id: str,
    payload: NotificationIntentCreate,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:sendReminder")
    try:
        return await queue_notification_intents(
            str(principal.tenant_id),
            principal.subject,
            scope,
            mission_id,
            payload,
        )
    except FieldRepositoryError as exc:
        raise _field_bad_request(exc) from exc


@router.get("/field/analytics")
async def get_field_analytics(principal: FieldViewer) -> dict[str, object]:
    scope = require_field_permission(principal, "feature:field_intelligence:analytics")
    return await field_analytics(str(principal.tenant_id), scope)


@router.get("/field/locations")
async def field_locations(principal: FieldViewer) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    items = await list_locations(str(principal.tenant_id), scope)
    return {"count": len(items), "items": items}


@router.put("/field/locations/{location_id}")
async def put_field_location(
    location_id: str,
    payload: LocationUpsert,
    principal: FieldViewer,
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:manageLocations")
    if location_id != payload.location_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="location path/body identity mismatch",
        )
    if not scope.unrestricted:
        allowed = location_id in scope.location_ids or (
            payload.region is not None and payload.region in scope.regions
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="location is outside Field Intelligence scope",
            )
    return await upsert_location(str(principal.tenant_id), payload)


@router.get("/field/templates")
async def field_templates(principal: FieldViewer) -> dict[str, object]:
    require_field_permission(principal, "module:field_intelligence:view")
    items = await list_templates(str(principal.tenant_id))
    return {"count": len(items), "items": items}


@router.post("/field/templates", status_code=status.HTTP_201_CREATED)
async def post_field_template(payload: TemplateCreate, principal: FieldViewer) -> dict[str, object]:
    require_field_permission(principal, "action:field_intelligence:manageTemplates")
    try:
        return await create_template(str(principal.tenant_id), principal.subject, payload)
    except ValueError as exc:
        raise _field_bad_request(exc) from exc


@router.put("/field/templates/{template_id}/{template_version}/evidence-policy")
async def put_field_template_evidence_policy(
    template_id: str,
    template_version: int,
    payload: EvidencePolicy,
    principal: FieldViewer,
) -> dict[str, object]:
    require_field_permission(principal, "action:field_intelligence:manageTemplates")
    try:
        return await set_template_evidence_policy(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            template_id=template_id,
            template_version=template_version,
            policy=payload,
        )
    except FieldOfflineSyncError as exc:
        raise _field_bad_request(exc) from exc
