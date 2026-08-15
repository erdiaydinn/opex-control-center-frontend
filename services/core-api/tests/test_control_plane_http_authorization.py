from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import Principal, get_current_principal
from app.main import app

CONTROL_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000a1")
CUSTOMER_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b2")


def principal(*, tenant_id: UUID, role: str) -> Principal:
    return Principal(
        subject="control-plane-http-boundary",
        tenant_id=tenant_id,
        roles=(role,),
        permissions=(),
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
@pytest.mark.parametrize("path", ["/v1/platform/authority", "/v1/platform/health"])
@pytest.mark.parametrize("role", ["platform_admin", "super_admin"])
async def test_customer_tenant_admin_is_rejected_by_control_plane_http_routes(
    monkeypatch,
    path: str,
    role: str,
) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))

    response = await get(
        path,
        principal(tenant_id=CUSTOMER_TENANT_ID, role=role),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "This tenant is not the EAY platform control plane"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/platform/authority", "/v1/platform/health"])
async def test_control_plane_http_routes_fail_closed_without_control_tenant_config(
    monkeypatch,
    path: str,
) -> None:
    monkeypatch.delenv("OPEX_PLATFORM_CONTROL_TENANT_ID", raising=False)

    response = await get(
        path,
        principal(tenant_id=CONTROL_TENANT_ID, role="platform_admin"),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Platform control-plane authority is not configured"


@pytest.mark.asyncio
async def test_control_plane_authority_http_route_allows_configured_platform_admin(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))

    response = await get(
        "/v1/platform/authority",
        principal(tenant_id=CONTROL_TENANT_ID, role="platform_admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authorized"] is True
    assert payload["tenant_id"] == str(CONTROL_TENANT_ID)
    assert payload["actor"] == "control-plane-http-boundary"
