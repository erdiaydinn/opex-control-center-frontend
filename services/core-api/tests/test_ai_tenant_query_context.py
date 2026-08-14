from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import app.ai_tenant_query_context_routes as query_routes
from app.core.ai_tenant_query_context import (
    ABSENT_QUERY_CONTEXT_FINGERPRINT,
    AiTenantQueryContext,
    AiTenantQueryContextConflict,
    AiTenantQueryContextInvalid,
    AiTenantQueryContextRecord,
    AiTenantQueryContextUpdate,
    ai_tenant_query_context_fingerprint,
)
from app.core.security import Principal, require_super_admin

TENANT = UUID("11111111-1111-4111-8111-111111111111")


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
            "path": "/v1/admin/ai-query-context",
            "raw_path": b"/v1/admin/ai-query-context",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    value.state.request_id = "query-context-request-1"
    return value


def context(*entity_ids: str) -> AiTenantQueryContext:
    return AiTenantQueryContext(
        version=1,
        entity_ids=entity_ids or ("TEST_ENTITY_A",),
        source_reference="data-catalog:tenant-entity-review-1",
    )


def test_context_normalizes_order_and_source_reference() -> None:
    value = AiTenantQueryContext(
        version=1,
        entity_ids=("TEST_ENTITY_B", "TEST_ENTITY_A"),
        source_reference="  data-catalog:review   1  ",
    )

    assert value.entity_ids == (
        "TEST_ENTITY_A",
        "TEST_ENTITY_B",
    )
    assert value.source_reference == "data-catalog:review 1"


def test_context_rejects_wildcards_spaces_duplicates_and_extra_fields() -> None:
    invalid_payloads = (
        {
            "version": 1,
            "entity_ids": [],
            "source_reference": "catalog:1",
        },
        {
            "version": 1,
            "entity_ids": ["*"],
            "source_reference": "catalog:1",
        },
        {
            "version": 1,
            "entity_ids": ["TEST%"],
            "source_reference": "catalog:1",
        },
        {
            "version": 1,
            "entity_ids": ["TEST ENTITY"],
            "source_reference": "catalog:1",
        },
        {
            "version": 1,
            "entity_ids": ["TEST_ENTITY", "test_entity"],
            "source_reference": "catalog:1",
        },
        {
            "version": 1,
            "entity_ids": ["TEST_ENTITY"],
            "source_reference": "catalog:1",
            "tenant_id": str(TENANT),
        },
    )

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            AiTenantQueryContext.model_validate(payload)


def test_context_fingerprint_is_stable_and_sensitive() -> None:
    first = context("TEST_ENTITY_A", "TEST_ENTITY_B")
    reordered = context("TEST_ENTITY_B", "TEST_ENTITY_A")
    changed = context("TEST_ENTITY_A")

    assert ai_tenant_query_context_fingerprint(first) == (
        ai_tenant_query_context_fingerprint(reordered)
    )
    assert ai_tenant_query_context_fingerprint(first) != (
        ai_tenant_query_context_fingerprint(changed)
    )
    assert len(ABSENT_QUERY_CONTEXT_FINGERPRINT) == 64


def test_query_context_routes_require_super_admin() -> None:
    for route in query_routes.router.routes:
        dependencies = {
            dependency.call
            for dependency in route.dependant.dependencies
        }
        assert require_super_admin in dependencies


def test_put_model_rejects_caller_tenant_and_bad_fingerprint() -> None:
    with pytest.raises(ValidationError):
        query_routes.PutAiTenantQueryContextRequest.model_validate(
            {
                "expected_record_fingerprint": "a" * 64,
                "context": context().model_dump(mode="json"),
                "tenant_id": str(TENANT),
            }
        )

    with pytest.raises(ValidationError):
        query_routes.PutAiTenantQueryContextRequest.model_validate(
            {
                "expected_record_fingerprint": "A" * 64,
                "context": context().model_dump(mode="json"),
            }
        )


@pytest.mark.asyncio
async def test_get_absent_context_returns_cas_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(**kwargs: object):
        assert kwargs["tenant_id"] == str(TENANT)
        return None

    monkeypatch.setattr(
        query_routes,
        "get_ai_tenant_query_context",
        fake_get,
    )

    response = await query_routes.get_tenant_query_context(
        principal()
    )

    assert response.configured is False
    assert response.context is None
    assert response.record_fingerprint == (
        ABSENT_QUERY_CONTEXT_FINGERPRINT
    )


@pytest.mark.asyncio
async def test_get_invalid_persisted_context_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_get(**_: object):
        raise AiTenantQueryContextInvalid("corrupt")

    monkeypatch.setattr(
        query_routes,
        "get_ai_tenant_query_context",
        fail_get,
    )

    with pytest.raises(HTTPException) as exc_info:
        await query_routes.get_tenant_query_context(
            principal()
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_put_maps_stale_context_to_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_put(**_: object):
        raise AiTenantQueryContextConflict("stale")

    monkeypatch.setattr(
        query_routes,
        "put_ai_tenant_query_context",
        fail_put,
    )

    with pytest.raises(HTTPException) as exc_info:
        await query_routes.put_tenant_query_context(
            query_routes.PutAiTenantQueryContextRequest(
                expected_record_fingerprint="a" * 64,
                context=context(),
            ),
            request(),
            principal(),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_put_uses_principal_tenant_and_actor_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_context = context()
    expected_fingerprint = ai_tenant_query_context_fingerprint(
        expected_context
    )

    async def fake_put(**kwargs: object):
        assert kwargs["tenant_id"] == str(TENANT)
        assert kwargs["actor_subject"] == "admin-1"
        assert kwargs["request_id"] == "query-context-request-1"
        assert kwargs["context"] == expected_context
        return AiTenantQueryContextUpdate(
            tenant_id=str(TENANT),
            context=expected_context,
            record_fingerprint=expected_fingerprint,
            changed=True,
        )

    monkeypatch.setattr(
        query_routes,
        "put_ai_tenant_query_context",
        fake_put,
    )

    response = await query_routes.put_tenant_query_context(
        query_routes.PutAiTenantQueryContextRequest(
            expected_record_fingerprint=(
                ABSENT_QUERY_CONTEXT_FINGERPRINT
            ),
            context=expected_context,
        ),
        request(),
        principal(),
    )

    assert response.tenant_id == str(TENANT)
    assert response.changed is True
    assert response.record_fingerprint == expected_fingerprint


def test_record_contract_does_not_need_caller_supplied_authority() -> None:
    record = AiTenantQueryContextRecord(
        tenant_id=str(TENANT),
        context=context(),
        record_fingerprint="a" * 64,
        updated_by="admin-1",
    )
    assert record.context.entity_ids == ("TEST_ENTITY_A",)
