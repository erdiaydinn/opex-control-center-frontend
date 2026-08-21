from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.core.ai_tenant_query_context as query_store
from app.core.ai_tenant_query_context import (
    ABSENT_QUERY_CONTEXT_FINGERPRINT,
    AiTenantQueryContext,
    put_ai_tenant_query_context,
)


class EmptyMappings:
    def first(self):
        return None


class EmptyResult:
    def mappings(self):
        return EmptyMappings()


class FailingConnection:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, statement, parameters=None):
        del statement, parameters
        self.calls += 1
        if self.calls == 3:
            raise RuntimeError("database unavailable")
        return EmptyResult()


class BeginContext:
    def __init__(self, connection: FailingConnection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        return False


@pytest.mark.asyncio
async def test_first_write_database_failure_is_not_misreported_as_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FailingConnection()
    fake_engine = SimpleNamespace(
        begin=lambda: BeginContext(connection)
    )
    monkeypatch.setattr(query_store, "engine", fake_engine)

    context = AiTenantQueryContext(
        version=1,
        entity_ids=("TEST_ENTITY_A",),
        source_reference="data-catalog:test-source",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await put_ai_tenant_query_context(
            tenant_id="11111111-1111-4111-8111-111111111111",
            expected_record_fingerprint=(
                ABSENT_QUERY_CONTEXT_FINGERPRINT
            ),
            context=context,
            actor_subject="admin-1",
            request_id="db-failure-test",
        )
