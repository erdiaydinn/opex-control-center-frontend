from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.permission_catalog import module_permission
from app.core.security import Principal, get_current_principal
from app.main import app

CONTROL_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000a1")
CUSTOMER_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b2")


def principal(
    *,
    tenant_id: UUID,
    role: str,
    permissions: tuple[str, ...] = (),
) -> Principal:
    return Principal(
        subject="intelligence-http-boundary",
        tenant_id=tenant_id,
        roles=(role,),
        permissions=permissions,
        permission_assignments=(),
        auth_mode="test",
    )


async def get(path: str, current: Principal):
    async def override_principal() -> Principal:
        return current

    app.dependency_overrides[get_current_principal] = override_principal
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            return await client.get(path, headers={"Authorization": "Bearer test"})
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_customer_platform_admin_cannot_fetch_security_guardian(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))
    response = await get(
        "/v1/platform/security-guardian/workspace",
        principal(tenant_id=CUSTOMER_TENANT_ID, role="platform_admin"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "This tenant is not the EAY platform control plane"


@pytest.mark.asyncio
async def test_control_plane_admin_can_fetch_read_only_security_guardian(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))
    response = await get(
        "/v1/platform/security-guardian/workspace",
        principal(tenant_id=CONTROL_TENANT_ID, role="platform_admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "eay_platform"
    assert payload["visibility"] == "platform_admin_only"
    assert payload["release_policy"]["automatic_production_remediation"] is False
    assert payload["release_policy"]["human_approval_required"] is True
    assert payload["findings"]["state"] == "unknown_without_observation_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "permission"),
    (
        ("/v1/jarvis/workspace", module_permission("jarvis")),
        ("/v1/insight/metrics", module_permission("insight")),
    ),
)
async def test_authenticated_user_without_module_permission_is_denied(
    path: str,
    permission: str,
) -> None:
    denied = await get(
        path,
        principal(tenant_id=CUSTOMER_TENANT_ID, role="viewer"),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["required_permission"] == permission

    allowed = await get(
        path,
        principal(
            tenant_id=CUSTOMER_TENANT_ID,
            role="viewer",
            permissions=(permission,),
        ),
    )
    assert allowed.status_code == 200
    assert allowed.json()["tenant_id"] == str(CUSTOMER_TENANT_ID)
