from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.authorization import require_control_plane_admin
from app.core.security import Principal

CONTROL_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000a1")
CUSTOMER_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b2")


def principal(*, tenant_id: UUID, roles: tuple[str, ...]) -> Principal:
    return Principal(
        subject="control-plane-boundary-test",
        tenant_id=tenant_id,
        roles=roles,
        permissions=(),
        permission_assignments=(),
        auth_mode="development",
    )


def test_platform_authority_and_health_routes_use_control_plane_authority() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )

    authority_block = source.split('@app.get("/v1/platform/authority"', maxsplit=1)[1]
    authority_signature = authority_block.split("@app.get", maxsplit=1)[0]
    assert "Depends(require_control_plane_admin)" in authority_signature
    assert "check_database" not in authority_signature
    assert "check_redis" not in authority_signature
    assert "PLATFORM_AGENT_URL" not in authority_signature

    health_block = source.split('@app.get("/v1/platform/health"', maxsplit=1)[1]
    health_signature = health_block.split("async def check_platform_agent", maxsplit=1)[0]
    assert "Depends(require_control_plane_admin)" in health_signature
    assert "Depends(require_platform_admin)" not in health_signature


@pytest.mark.asyncio
async def test_customer_platform_admin_cannot_enter_control_plane(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))

    with pytest.raises(HTTPException) as exc_info:
        await require_control_plane_admin(
            principal(tenant_id=CUSTOMER_TENANT_ID, roles=("platform_admin",))
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "This tenant is not the EAY platform control plane"


@pytest.mark.asyncio
async def test_customer_super_admin_cannot_enter_control_plane(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))

    with pytest.raises(HTTPException) as exc_info:
        await require_control_plane_admin(
            principal(tenant_id=CUSTOMER_TENANT_ID, roles=("super_admin",))
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_control_tenant_without_platform_role_is_denied(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))

    with pytest.raises(HTTPException) as exc_info:
        await require_control_plane_admin(
            principal(tenant_id=CONTROL_TENANT_ID, roles=("viewer",))
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "EAY platform administrator authority is required"


@pytest.mark.asyncio
async def test_control_plane_platform_admin_is_allowed(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", str(CONTROL_TENANT_ID))
    expected = principal(tenant_id=CONTROL_TENANT_ID, roles=("platform_admin",))

    actual = await require_control_plane_admin(expected)

    assert actual is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("configured_value", [None, "not-a-uuid"])
async def test_control_plane_authority_fails_closed_when_configuration_is_unavailable(
    monkeypatch,
    configured_value: str | None,
) -> None:
    if configured_value is None:
        monkeypatch.delenv("OPEX_PLATFORM_CONTROL_TENANT_ID", raising=False)
    else:
        monkeypatch.setenv("OPEX_PLATFORM_CONTROL_TENANT_ID", configured_value)

    with pytest.raises(HTTPException) as exc_info:
        await require_control_plane_admin(
            principal(tenant_id=CONTROL_TENANT_ID, roles=("platform_admin",))
        )

    assert exc_info.value.status_code == 503
