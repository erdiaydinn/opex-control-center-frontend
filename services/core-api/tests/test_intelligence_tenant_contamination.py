import json
from uuid import UUID

from app.core.permission_catalog import (
    action_permission,
    feature_permission,
    module_permission,
)
from app.core.security import PermissionAssignment, Principal
from app.intelligence_routes import build_insight_metrics, build_jarvis_workspace

TENANT_A = UUID("00000000-0000-0000-0000-0000000092a1")
TENANT_B = UUID("00000000-0000-0000-0000-0000000092b1")


def _principal(*, tenant_id: UUID, subject: str, store_name: str) -> Principal:
    ops_permission = action_permission("ai_assistant", "executeOpsRead")
    return Principal(
        subject=subject,
        tenant_id=tenant_id,
        roles=("operator",),
        permissions=(
            module_permission("jarvis"),
            feature_permission("jarvis", "assistant"),
            action_permission("jarvis", "ask"),
            module_permission("insight"),
            feature_permission("insight", "canonicalMetrics"),
            action_permission("insight", "view"),
            ops_permission,
        ),
        permission_assignments=(
            PermissionAssignment(
                key=ops_permission,
                role_key="operator",
                scope={
                    "ai_data_scope": {
                        "version": 1,
                        "store_names": [store_name],
                    }
                },
            ),
        ),
        auth_mode="test",
    )


def test_sequential_intelligence_responses_do_not_cross_contaminate_tenants() -> None:
    principal_a = _principal(
        tenant_id=TENANT_A,
        subject="tenant-a-user",
        store_name="Tenant A Private Store",
    )
    principal_b = _principal(
        tenant_id=TENANT_B,
        subject="tenant-b-user",
        store_name="Tenant B Private Store",
    )

    jarvis_a = build_jarvis_workspace(principal_a)
    insight_a = build_insight_metrics(principal_a)
    jarvis_b = build_jarvis_workspace(principal_b)
    insight_b = build_insight_metrics(principal_b)

    assert jarvis_a["tenant_id"] == str(TENANT_A)
    assert insight_a["tenant_id"] == str(TENANT_A)
    assert jarvis_b["tenant_id"] == str(TENANT_B)
    assert insight_b["tenant_id"] == str(TENANT_B)
    assert jarvis_a["actor"] == "tenant-a-user"
    assert jarvis_b["actor"] == "tenant-b-user"

    serialized_a = json.dumps({"jarvis": jarvis_a, "insight": insight_a})
    serialized_b = json.dumps({"jarvis": jarvis_b, "insight": insight_b})

    assert str(TENANT_B) not in serialized_a
    assert "tenant-b-user" not in serialized_a
    assert "Tenant B Private Store" not in serialized_a
    assert str(TENANT_A) not in serialized_b
    assert "tenant-a-user" not in serialized_b
    assert "Tenant A Private Store" not in serialized_b

    # Server-authoritative scope values are authorization input, not browser payload.
    assert "Tenant A Private Store" not in serialized_a
    assert "Tenant B Private Store" not in serialized_b
