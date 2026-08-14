from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import app.ai_data_scope_admin_routes as admin_routes
from app.core.ai_data_scope import AiDataScope
from app.core.ai_data_scope_admin import (
    AiDataScopeAssignmentConflict,
    AiDataScopeAssignmentNotFound,
    AiDataScopeAssignmentRecord,
    AiDataScopeAssignmentUpdate,
    permission_scope_record_fingerprint,
)
from app.core.ai_tool_authorization import SCOPE_PERMISSION_KEYS
from app.core.security import Principal, require_super_admin

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OPS_PERMISSION = SCOPE_PERMISSION_KEYS["ops:read"]


def principal() -> Principal:
    return Principal(
        subject="admin-1",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=(),
        permission_assignments=(),
        auth_mode="oidc",
    )


def request() -> Request:
    value = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "PUT",
            "scheme": "http",
            "path": "/v1/admin/ai-data-scopes/super_admin/x",
            "raw_path": b"/v1/admin/ai-data-scopes/super_admin/x",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    value.state.request_id = "request-1"
    return value


def data_scope(*stores: str) -> AiDataScope:
    return AiDataScope(
        version=1,
        store_names=stores,
    )


def test_admin_routes_require_super_admin() -> None:
    assert admin_routes.router.routes

    for route in admin_routes.router.routes:
        dependencies = {
            dependency.call
            for dependency in route.dependant.dependencies
        }
        assert require_super_admin in dependencies


def test_update_model_rejects_extra_authorization_fields() -> None:
    with pytest.raises(ValidationError):
        admin_routes.UpdateAiDataScopeAssignmentRequest.model_validate(
            {
                "expected_record_fingerprint": "a" * 64,
                "data_scope": {
                    "version": 1,
                    "store_names": ["Fulya"],
                },
                "permission_key": OPS_PERMISSION,
            }
        )


def test_update_model_rejects_invalid_fingerprint_and_scope() -> None:
    for payload in (
        {
            "expected_record_fingerprint": "A" * 64,
            "data_scope": {
                "version": 1,
                "store_names": ["Fulya"],
            },
        },
        {
            "expected_record_fingerprint": "a" * 64,
            "data_scope": {
                "version": 1,
                "store_names": ["*"],
            },
        },
    ):
        with pytest.raises(ValidationError):
            admin_routes.UpdateAiDataScopeAssignmentRequest.model_validate(
                payload
            )


@pytest.mark.asyncio
async def test_listing_does_not_trust_legacy_empty_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_raw = {
        "ai_data_scope": {
            "version": 1,
            "store_names": ["Fulya"],
        }
    }
    empty_raw: dict[str, object] = {}

    async def fake_list(**_: object):
        return (
            AiDataScopeAssignmentRecord(
                role_key="super_admin",
                role_name="Super Admin",
                is_system=True,
                permission_key=OPS_PERMISSION,
                raw_scope=empty_raw,
                record_fingerprint=permission_scope_record_fingerprint(
                    empty_raw
                ),
            ),
            AiDataScopeAssignmentRecord(
                role_key="ops_admin",
                role_name="Ops Admin",
                is_system=False,
                permission_key=OPS_PERMISSION,
                raw_scope=valid_raw,
                record_fingerprint=permission_scope_record_fingerprint(
                    valid_raw
                ),
            ),
        )

    monkeypatch.setattr(
        admin_routes,
        "list_ai_data_scope_assignments",
        fake_list,
    )

    response = await admin_routes.get_ai_data_scope_assignments(
        principal()
    )

    assert response.count == 2
    assert response.items[0].status == "unconfigured"
    assert response.items[0].data_scope is None
    assert response.items[1].status == "configured"
    assert response.items[1].data_scope is not None
    assert response.items[1].data_scope.store_names == ("Fulya",)


@pytest.mark.asyncio
async def test_update_rejects_non_ai_permission_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def should_not_run(**_: object):
        pytest.fail("persistence must not run")

    monkeypatch.setattr(
        admin_routes,
        "update_ai_data_scope_assignment",
        should_not_run,
    )

    with pytest.raises(HTTPException) as exc_info:
        await admin_routes.put_ai_data_scope_assignment(
            "super_admin",
            "action:workforce:manageEmployees",
            admin_routes.UpdateAiDataScopeAssignmentRequest(
                expected_record_fingerprint="a" * 64,
                data_scope=data_scope("Fulya"),
            ),
            request(),
            principal(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status_code"),
    [
        (AiDataScopeAssignmentNotFound("missing"), 404),
        (AiDataScopeAssignmentConflict("stale"), 409),
    ],
)
async def test_update_maps_persistence_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status_code: int,
) -> None:
    async def fail(**_: object):
        raise failure

    monkeypatch.setattr(
        admin_routes,
        "update_ai_data_scope_assignment",
        fail,
    )

    with pytest.raises(HTTPException) as exc_info:
        await admin_routes.put_ai_data_scope_assignment(
            "super_admin",
            OPS_PERMISSION,
            admin_routes.UpdateAiDataScopeAssignmentRequest(
                expected_record_fingerprint="a" * 64,
                data_scope=data_scope("Fulya"),
            ),
            request(),
            principal(),
        )

    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_success_returns_only_server_persistence_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = data_scope("Fulya")

    async def fake_update(**kwargs: object):
        assert kwargs["tenant_id"] == str(TENANT)
        assert kwargs["actor_subject"] == "admin-1"
        assert kwargs["request_id"] == "request-1"
        return AiDataScopeAssignmentUpdate(
            role_key="super_admin",
            permission_key=OPS_PERMISSION,
            record_fingerprint="b" * 64,
            data_scope=scope,
            changed=True,
        )

    monkeypatch.setattr(
        admin_routes,
        "update_ai_data_scope_assignment",
        fake_update,
    )

    response = await admin_routes.put_ai_data_scope_assignment(
        "super_admin",
        OPS_PERMISSION,
        admin_routes.UpdateAiDataScopeAssignmentRequest(
            expected_record_fingerprint="a" * 64,
            data_scope=scope,
        ),
        request(),
        principal(),
    )

    assert response.changed is True
    assert response.record_fingerprint == "b" * 64
    assert response.data_scope.store_names == ("Fulya",)
