import json
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.authorization import require_control_plane_admin
from app.core.permission_catalog import (
    action_permission,
    feature_permission,
    module_permission,
)
from app.core.security import PermissionAssignment, Principal
from app.intelligence_routes import (
    build_insight_metrics,
    build_jarvis_workspace,
    build_planogram_readiness,
    build_security_guardian_workspace,
    insight_view_guard,
    jarvis_view_guard,
    router,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000009201")
CONTROL_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000a1")


def _principal(
    *,
    role: str = "operator",
    tenant_id: UUID = TENANT_ID,
    include_jarvis: bool = True,
    include_insight: bool = True,
) -> Principal:
    ops_permission = action_permission("ai_assistant", "executeOpsRead")
    permissions = [
        module_permission("planogram"),
        feature_permission("planogram", "layoutView"),
        action_permission("planogram", "view"),
        ops_permission,
    ]
    if include_jarvis:
        permissions.extend(
            (
                module_permission("jarvis"),
                feature_permission("jarvis", "assistant"),
                action_permission("jarvis", "ask"),
            )
        )
    if include_insight:
        permissions.extend(
            (
                module_permission("insight"),
                feature_permission("insight", "canonicalMetrics"),
                action_permission("insight", "view"),
            )
        )

    return Principal(
        subject="tenant-user",
        tenant_id=tenant_id,
        roles=(role,),
        permissions=tuple(permissions),
        permission_assignments=(
            PermissionAssignment(
                key=ops_permission,
                role_key=role,
                scope={
                    "ai_data_scope": {
                        "version": 1,
                        "store_names": ["Fulya"],
                    }
                },
            ),
        ),
        auth_mode="test",
    )


def test_jarvis_workspace_is_tenant_bound_and_fail_closed() -> None:
    payload = build_jarvis_workspace(_principal())
    assert payload["tenant_id"] == str(TENANT_ID)
    assert payload["actor"] == "tenant-user"
    assert payload["security_guardian_visible"] is False
    ops = next(item for item in payload["tools"] if item["tool"] == "ops_kpi_query")
    assert ops["grant_eligible"] is True
    assert ops["query_contract_id"] == "ops.kpi.orders.v2"
    assert ops["runtime_ready"] is False
    assert ops["activation_state"] == "blocked"
    assert ops["blockers"]
    serialized = json.dumps(payload).lower()
    assert "select " not in serialized
    assert " from " not in serialized


def test_insight_uses_canonical_orders_v2_readiness() -> None:
    payload = build_insight_metrics(_principal())
    assert payload["tenant_id"] == str(TENANT_ID)
    metric = payload["metrics"][0]
    assert metric["metric_id"] == "ops.kpi.orders.v2"
    assert metric["production_ready"] is False
    assert metric["activation_state"] == "candidate"
    assert metric["tenant_discriminator"] == {
        "expression": "entity.id",
        "authority": "candidate_unverified",
    }
    assert metric["evidence"] == {
        "schema": False,
        "array_parameter_adapter": False,
        "cross_tenant_proof": False,
    }
    assert metric["blockers"]
    assert "sql" not in metric


@pytest.mark.asyncio
async def test_jarvis_and_insight_routes_require_module_permissions() -> None:
    route_by_path = {
        getattr(item, "path", None): item
        for item in router.routes
    }
    assert any(
        dependency.call is jarvis_view_guard
        for dependency in route_by_path["/v1/jarvis/workspace"].dependant.dependencies
    )
    assert any(
        dependency.call is insight_view_guard
        for dependency in route_by_path["/v1/insight/metrics"].dependant.dependencies
    )

    allowed = _principal()
    assert await jarvis_view_guard(allowed) is allowed
    assert await insight_view_guard(allowed) is allowed

    with pytest.raises(HTTPException) as jarvis_exc:
        await jarvis_view_guard(_principal(include_jarvis=False))
    assert jarvis_exc.value.status_code == 403
    assert jarvis_exc.value.detail["required_permission"] == "module:jarvis:view"

    with pytest.raises(HTTPException) as insight_exc:
        await insight_view_guard(_principal(include_insight=False))
    assert insight_exc.value.status_code == 403
    assert insight_exc.value.detail["required_permission"] == "module:insight:view"


def test_planogram_readiness_preserves_physical_truth_and_security_gates() -> None:
    payload = build_planogram_readiness(_principal())
    assert payload["tenant_id"] == str(TENANT_ID)
    assert payload["authority"] == "eay_core_api"
    assert payload["engine"] == {
        "contract": "deterministic-physical-truth",
        "runtime_mode": "domain_library",
        "legacy_bridge_enabled": False,
        "parallel_planai_auth_allowed": False,
    }
    assert payload["physical_truth"]["evidence_state"] == "external_required"
    assert payload["physical_truth"]["verified_attestation"] is None
    assert set(payload["physical_truth"]["required_evidence"]) == {
        "approved_sku_dimensions",
        "product_image_linkage",
        "store_dna",
        "fixture_geometry_capacity",
        "physical_layout_aisle",
        "pallet_fixture_authority",
    }
    assert payload["solver_optimizer_allowed"] is False
    assert payload["production_ready"] is False


def test_security_guardian_unknown_without_observation_evidence() -> None:
    payload = build_security_guardian_workspace(_principal(role="platform_admin"))
    assert payload["scope"] == "eay_platform"
    assert payload["visibility"] == "platform_admin_only"
    assert payload["mode"] == "read_only_assessment"
    assert payload["production_ready"] is False
    assert payload["security_posture"] == "not_scored_without_observation_evidence"
    assert payload["last_observed_at"] is None
    assert payload["findings"]["state"] == "unknown_without_observation_evidence"
    assert payload["findings"]["items"] == []
    assert set(payload["findings"]["counts"].values()) == {None}
    assert {item["source_id"] for item in payload["threat_intelligence"]} == {
        "cisa_kev",
        "osv",
        "github_advisory",
    }
    assert {item["integration_state"] for item in payload["threat_intelligence"]} == {
        "not_connected"
    }
    assert payload["release_policy"] == {
        "customer_visibility": False,
        "automatic_production_remediation": False,
        "human_approval_required": True,
        "zero_findings_without_evidence_allowed": False,
    }

    controls = {item["control_id"]: item for item in payload["controls"]}
    assert controls["dependency_inventory"] == {
        "control_id": "dependency_inventory",
        "implementation_state": "implemented_build_evidence",
        "evidence_state": "cyclonedx_prebuild_and_build_ci",
    }
    assert payload["dependency_inventory"] == {
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
    }
    assert "dependency_sbom_inventory_missing" not in payload["blockers"]
    assert "resolved_python_transitive_dependency_graph_missing" not in payload["blockers"]
    assert "resolved_android_dependency_graph_missing" not in payload["blockers"]
    assert "runtime_deployment_sbom_observation_missing" in payload["blockers"]
    assert "reachable_code_analysis_missing" in payload["blockers"]
    assert "tenant_id" not in payload


@pytest.mark.asyncio
async def test_security_guardian_route_uses_control_plane_gate(monkeypatch) -> None:
    route = next(
        item
        for item in router.routes
        if getattr(item, "path", None) == "/v1/platform/security-guardian/workspace"
    )
    assert any(
        dependency.call is require_control_plane_admin
        for dependency in route.dependant.dependencies
    )

    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))
    control_admin = _principal(role="platform_admin", tenant_id=CONTROL_TENANT_ID)
    assert await require_control_plane_admin(control_admin) is control_admin

    with pytest.raises(HTTPException) as customer_exc:
        await require_control_plane_admin(_principal(role="platform_admin"))
    assert customer_exc.value.status_code == 403
    assert customer_exc.value.detail == "This tenant is not the EAY platform control plane"

    with pytest.raises(HTTPException) as role_exc:
        await require_control_plane_admin(_principal(role="operator", tenant_id=CONTROL_TENANT_ID))
    assert role_exc.value.status_code == 403
    assert role_exc.value.detail == "EAY platform administrator authority is required"
