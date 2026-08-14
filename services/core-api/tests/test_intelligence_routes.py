import json
from uuid import UUID

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
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000009201")


def _principal() -> Principal:
    ops_permission = action_permission("ai_assistant", "executeOpsRead")
    permissions = (
        module_permission("jarvis"),
        feature_permission("jarvis", "assistant"),
        action_permission("jarvis", "ask"),
        module_permission("insight"),
        feature_permission("insight", "canonicalMetrics"),
        action_permission("insight", "view"),
        module_permission("planogram"),
        feature_permission("planogram", "layoutView"),
        action_permission("planogram", "view"),
        ops_permission,
    )
    return Principal(
        subject="tenant-user",
        tenant_id=TENANT_ID,
        roles=("operator",),
        permissions=permissions,
        permission_assignments=(
            PermissionAssignment(
                key=ops_permission,
                role_key="operator",
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
