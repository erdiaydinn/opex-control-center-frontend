import pytest

from app.core.ai_query_context_binding import (
    AiQueryContextBindingError,
    bind_query_context_to_execution,
)
from app.core.ai_tenant_query_context import (
    AiTenantQueryContext,
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
)


def _record(tenant_id: str = "tenant-a") -> AiTenantQueryContextRecord:
    context = AiTenantQueryContext(
        version=1,
        entity_ids=("YS_TR",),
        source_reference="admin-config:test",
    )
    return AiTenantQueryContextRecord(
        tenant_id=tenant_id,
        context=context,
        record_fingerprint=ai_tenant_query_context_fingerprint(context),
        updated_by="tester",
    )


def test_binding_is_deterministic_and_commits_to_context_and_execution() -> None:
    first = bind_query_context_to_execution(
        tenant_id="tenant-a",
        query_context=_record(),
        execution_scope_fingerprint="a" * 64,
    )
    second = bind_query_context_to_execution(
        tenant_id="tenant-a",
        query_context=_record(),
        execution_scope_fingerprint="a" * 64,
    )
    changed_execution = bind_query_context_to_execution(
        tenant_id="tenant-a",
        query_context=_record(),
        execution_scope_fingerprint="b" * 64,
    )

    assert first == second
    assert first.entity_ids == ("YS_TR",)
    assert first.execution_context_fingerprint != changed_execution.execution_context_fingerprint


def test_missing_context_fails_closed() -> None:
    with pytest.raises(AiQueryContextBindingError, match="not configured"):
        bind_query_context_to_execution(
            tenant_id="tenant-a",
            query_context=None,
            execution_scope_fingerprint="a" * 64,
        )


def test_cross_tenant_context_fails_closed() -> None:
    with pytest.raises(AiQueryContextBindingError, match="does not match"):
        bind_query_context_to_execution(
            tenant_id="tenant-b",
            query_context=_record("tenant-a"),
            execution_scope_fingerprint="a" * 64,
        )


@pytest.mark.parametrize("value", ["", "a" * 63, "g" * 64])
def test_invalid_execution_fingerprint_fails_closed(value: str) -> None:
    with pytest.raises(AiQueryContextBindingError, match="not SHA-256"):
        bind_query_context_to_execution(
            tenant_id="tenant-a",
            query_context=_record(),
            execution_scope_fingerprint=value,
        )
