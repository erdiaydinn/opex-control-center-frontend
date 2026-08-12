from uuid import UUID

import pytest

from app.core.ai_tool_authorization import AiToolCapability
from app.core.jarvis_execution_idempotency import (
    JARVIS_IDEMPOTENCY_DEFAULT_TTL_SECONDS,
    JARVIS_IDEMPOTENCY_MAX_TTL_SECONDS,
    JarvisIdempotencyInvalid,
    PostgresJarvisExecutionIdempotencyStore,
    actor_subject_sha256,
    build_execution_request_fingerprint,
    idempotency_key_sha256,
    validate_idempotency_key,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def capability(*, fingerprint: str = "a" * 64) -> AiToolCapability:
    return AiToolCapability(
        tenant_id=TENANT,
        actor_subject="user-sensitive-subject",
        tool="ops_kpi_query",
        granted_scopes=("ops:read",),
        permission_keys=("action:ai_assistant:executeOpsRead",),
        authorizing_roles=("super_admin",),
        authorization_fingerprint=fingerprint,
    )


def test_idempotency_key_contract_is_strict() -> None:
    valid = "req-20260812-abcdef0123456789"
    assert validate_idempotency_key(valid) == valid

    for invalid in (
        "short",
        " contains-space-123456",
        "comma,value,123456789",
        "x" * 129,
        "ümlaut-request-123456",
    ):
        with pytest.raises(JarvisIdempotencyInvalid):
            validate_idempotency_key(invalid)


def test_raw_actor_and_client_key_are_one_way_hashed() -> None:
    actor = "user-sensitive-subject"
    key = "req-20260812-abcdef0123456789"

    actor_hash = actor_subject_sha256(actor)
    key_hash = idempotency_key_sha256(key)

    assert len(actor_hash) == 64
    assert len(key_hash) == 64
    assert actor not in actor_hash
    assert key not in key_hash
    assert actor_hash != key_hash


def test_request_fingerprint_binds_authorization_and_server_policy() -> None:
    base = build_execution_request_fingerprint(
        capability(),
        arguments_sha256="b" * 64,
        reason_sha256="c" * 64,
        execution_policy={
            "execute": True,
            "maximum_bytes_billed": 100,
            "max_rows": 50,
        },
    )
    changed_policy = build_execution_request_fingerprint(
        capability(),
        arguments_sha256="b" * 64,
        reason_sha256="c" * 64,
        execution_policy={
            "execute": True,
            "maximum_bytes_billed": 200,
            "max_rows": 50,
        },
    )
    changed_authority = build_execution_request_fingerprint(
        capability(fingerprint="d" * 64),
        arguments_sha256="b" * 64,
        reason_sha256="c" * 64,
        execution_policy={
            "execute": True,
            "maximum_bytes_billed": 100,
            "max_rows": 50,
        },
    )

    assert len(base) == 64
    assert base != changed_policy
    assert base != changed_authority


def test_store_ttl_is_strictly_bounded() -> None:
    class PlaceholderEngine:
        pass

    for invalid in (
        True,
        0,
        59,
        JARVIS_IDEMPOTENCY_MAX_TTL_SECONDS + 1,
    ):
        with pytest.raises(ValueError):
            PostgresJarvisExecutionIdempotencyStore(
                PlaceholderEngine(),  # type: ignore[arg-type]
                ttl_seconds=invalid,  # type: ignore[arg-type]
            )

    store = PostgresJarvisExecutionIdempotencyStore(
        PlaceholderEngine(),  # type: ignore[arg-type]
        ttl_seconds=JARVIS_IDEMPOTENCY_DEFAULT_TTL_SECONDS,
    )
    assert store is not None
