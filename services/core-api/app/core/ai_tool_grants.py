"""Single-use execution grants for authorized Jarvis tool calls.

A capability answers *what* an actor may do and *which role-scoped data* it
may touch. A tool grant binds that capability, the tenant's authoritative
query discriminator context, and the current version-controlled downstream
query contract to exactly one concrete invocation and can be consumed once.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.ai_data_scope import (
    AiDataScope,
    AiDataScopeError,
    ai_data_scope_fingerprint,
    validate_ai_data_scope_invocation,
)
from app.core.ai_query_contract_policy import (
    AiQueryContractPolicy,
    ai_execution_scope_fingerprint,
    ai_query_contract_policy_fingerprint,
    get_ai_query_contract_policy,
)
from app.core.ai_tenant_query_context import (
    AiTenantQueryContextInvalid,
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
    get_ai_tenant_query_context,
)
from app.core.ai_tool_authorization import (
    TOOL_REQUIRED_SCOPES,
    AiToolCapability,
    AiToolName,
)

AI_TOOL_GRANT_DEFAULT_TTL_SECONDS = 30
AI_TOOL_GRANT_MAX_TTL_SECONDS = 60
AI_TOOL_GRANT_VERSION = 4
SHA256_PATTERN = r"^[0-9a-f]{64}$"
TenantQueryContextLoader = Callable[
    [str],
    Awaitable[AiTenantQueryContextRecord | None],
]


class AiToolGrantError(PermissionError):
    """Base denial for Jarvis single-use execution grants."""


class AiToolGrantInvalid(AiToolGrantError):
    """The invocation cannot be represented by the grant contract."""


class AiToolGrantUnavailable(AiToolGrantError):
    """The distributed grant authority is unavailable."""


class AiToolGrantTenantContextUnavailable(AiToolGrantError):
    """The authoritative tenant query context cannot be used safely."""


class AiToolGrantReplayOrExpired(AiToolGrantError):
    """The opaque grant has already been consumed or has expired."""


class AiToolGrantBindingMismatch(AiToolGrantError):
    """The grant was issued for a different invocation or security contract."""


class AiToolGrantBinding(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    version: Literal[4]
    tenant_id: UUID
    actor_subject: str = Field(
        min_length=1,
        max_length=512,
    )
    tool: AiToolName
    data_scope: AiDataScope
    data_scope_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    tenant_query_context_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    query_contract_id: str = Field(
        min_length=1,
        max_length=160,
    )
    query_contract_revision: int = Field(ge=1)
    query_contract_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    execution_scope_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    arguments_sha256: str = Field(
        pattern=SHA256_PATTERN
    )
    reason_sha256: str = Field(
        pattern=SHA256_PATTERN
    )
    authorization_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )


class IssuedAiToolGrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: SecretStr
    expires_in_seconds: int
    binding: AiToolGrantBinding


class AuthorizedAiToolInvocation(BaseModel):
    """Trusted execution context recovered after atomic grant consumption."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    binding: AiToolGrantBinding
    tenant_entity_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=16,
    )


async def _default_tenant_query_context_loader(
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    return await get_ai_tenant_query_context(
        tenant_id=tenant_id
    )


def _validate_json_value(
    value: Any,
    *,
    path: str,
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return

    if isinstance(value, float):
        if not math.isfinite(value):
            raise AiToolGrantInvalid(
                f"Non-finite number at {path}"
            )
        return

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AiToolGrantInvalid(
                    f"Non-string object key at {path}"
                )
            _validate_json_value(
                child,
                path=f"{path}.{key}",
            )
        return

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, child in enumerate(value):
            _validate_json_value(
                child,
                path=f"{path}[{index}]",
            )
        return

    raise AiToolGrantInvalid(
        f"Unsupported JSON value at {path}"
    )


def canonical_arguments_sha256(
    arguments: Mapping[str, Any],
) -> str:
    if not isinstance(arguments, Mapping):
        raise AiToolGrantInvalid(
            "Tool arguments must be an object"
        )

    _validate_json_value(
        arguments,
        path="$",
    )

    try:
        encoded = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AiToolGrantInvalid(
            "Tool arguments are not canonical JSON"
        ) from exc

    return hashlib.sha256(encoded).hexdigest()


def canonical_reason_sha256(reason: str) -> str:
    if not isinstance(reason, str):
        raise AiToolGrantInvalid(
            "Tool execution reason must be text"
        )

    normalized = " ".join(reason.split())

    if not normalized or len(normalized) > 1000:
        raise AiToolGrantInvalid(
            "Tool execution reason is invalid"
        )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _validate_scope_binding(
    *,
    tool: str,
    arguments: Mapping[str, Any],
    data_scope: AiDataScope,
    data_scope_fingerprint: str,
) -> None:
    expected_fingerprint = (
        ai_data_scope_fingerprint(data_scope)
    )
    if data_scope_fingerprint != expected_fingerprint:
        raise AiToolGrantInvalid(
            "AI tool data scope fingerprint does not match"
        )

    try:
        validate_ai_data_scope_invocation(
            tool=tool,
            arguments=arguments,
            data_scope=data_scope,
        )
    except AiDataScopeError as exc:
        raise AiToolGrantInvalid(
            "AI tool invocation exceeds authorized data scope"
        ) from exc


def _query_contract_binding(
    *,
    policy: AiQueryContractPolicy,
    data_scope_fingerprint: str,
    tenant_query_context_fingerprint: str,
) -> tuple[str, str]:
    policy_fingerprint = (
        ai_query_contract_policy_fingerprint(policy)
    )
    execution_fingerprint = ai_execution_scope_fingerprint(
        query_contract_fingerprint=policy_fingerprint,
        data_scope_fingerprint=data_scope_fingerprint,
        tenant_query_context_fingerprint=(
            tenant_query_context_fingerprint
        ),
    )
    return policy_fingerprint, execution_fingerprint


def build_ai_tool_grant_binding(
    capability: AiToolCapability,
    *,
    tenant_query_context_fingerprint: str,
    arguments: Mapping[str, Any],
    reason: str,
) -> AiToolGrantBinding:
    query_policy = get_ai_query_contract_policy(
        capability.tool
    )

    _validate_scope_binding(
        tool=capability.tool,
        arguments=arguments,
        data_scope=capability.data_scope,
        data_scope_fingerprint=(
            capability.data_scope_fingerprint
        ),
    )

    (
        query_contract_fingerprint,
        execution_scope_fingerprint,
    ) = _query_contract_binding(
        policy=query_policy,
        data_scope_fingerprint=(
            capability.data_scope_fingerprint
        ),
        tenant_query_context_fingerprint=(
            tenant_query_context_fingerprint
        ),
    )

    return AiToolGrantBinding(
        version=AI_TOOL_GRANT_VERSION,
        tenant_id=capability.tenant_id,
        actor_subject=capability.actor_subject,
        tool=capability.tool,
        data_scope=capability.data_scope,
        data_scope_fingerprint=(
            capability.data_scope_fingerprint
        ),
        tenant_query_context_fingerprint=(
            tenant_query_context_fingerprint
        ),
        query_contract_id=query_policy.contract_id,
        query_contract_revision=(
            query_policy.contract_revision
        ),
        query_contract_fingerprint=(
            query_contract_fingerprint
        ),
        execution_scope_fingerprint=(
            execution_scope_fingerprint
        ),
        arguments_sha256=canonical_arguments_sha256(
            arguments
        ),
        reason_sha256=canonical_reason_sha256(reason),
        authorization_fingerprint=(
            capability.authorization_fingerprint
        ),
    )


class RedisAiToolGrantStore:
    """Issue and atomically consume opaque Jarvis execution grants."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        key_prefix: str = "opex:{ai}:tool-grant",
        tenant_query_context_loader: (
            TenantQueryContextLoader | None
        ) = None,
    ) -> None:
        if (
            not isinstance(key_prefix, str)
            or not key_prefix
            or len(key_prefix) > 128
        ):
            raise ValueError(
                "AI tool grant key prefix is invalid"
            )

        self._redis = redis_client
        self._key_prefix = key_prefix
        self._tenant_query_context_loader = (
            tenant_query_context_loader
            or _default_tenant_query_context_loader
        )

    def _key(self, token: str) -> str:
        if (
            not isinstance(token, str)
            or len(token) < 32
            or len(token) > 256
        ):
            raise AiToolGrantInvalid(
                "AI tool grant token is invalid"
            )

        digest = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        return f"{self._key_prefix}:{digest}"

    async def _load_tenant_query_context(
        self,
        *,
        tenant_id: UUID,
    ) -> AiTenantQueryContextRecord:
        expected_tenant_id = str(tenant_id)
        try:
            record = await self._tenant_query_context_loader(
                expected_tenant_id
            )
        except AiTenantQueryContextInvalid as exc:
            raise AiToolGrantTenantContextUnavailable(
                "Tenant query context is invalid"
            ) from exc
        except Exception as exc:
            raise AiToolGrantTenantContextUnavailable(
                "Tenant query context authority is unavailable"
            ) from exc

        if record is None:
            raise AiToolGrantTenantContextUnavailable(
                "Tenant query context is not configured"
            )

        expected_fingerprint = (
            ai_tenant_query_context_fingerprint(
                record.context
            )
        )
        if (
            record.tenant_id != expected_tenant_id
            or record.record_fingerprint
            != expected_fingerprint
        ):
            raise AiToolGrantTenantContextUnavailable(
                "Tenant query context authority is inconsistent"
            )

        return record

    async def _consume_stored_binding(
        self,
        *,
        token: str,
    ) -> AiToolGrantBinding:
        key = self._key(token)

        try:
            payload = await self._redis.getdel(key)
        except RedisError as exc:
            raise AiToolGrantUnavailable(
                "AI tool grant authority is unavailable"
            ) from exc

        if payload is None:
            raise AiToolGrantReplayOrExpired(
                "AI tool grant is unavailable"
            )

        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        try:
            return AiToolGrantBinding.model_validate_json(
                payload
            )
        except (ValueError, TypeError) as exc:
            raise AiToolGrantInvalid(
                "Stored AI tool grant is invalid"
            ) from exc

    async def issue(
        self,
        capability: AiToolCapability,
        *,
        arguments: Mapping[str, Any],
        reason: str,
        ttl_seconds: int = (
            AI_TOOL_GRANT_DEFAULT_TTL_SECONDS
        ),
    ) -> IssuedAiToolGrant:
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= AI_TOOL_GRANT_MAX_TTL_SECONDS
        ):
            raise ValueError(
                "AI tool grant TTL is invalid"
            )

        tenant_query_context = await self._load_tenant_query_context(
            tenant_id=capability.tenant_id
        )
        binding = build_ai_tool_grant_binding(
            capability,
            tenant_query_context_fingerprint=(
                tenant_query_context.record_fingerprint
            ),
            arguments=arguments,
            reason=reason,
        )

        token = secrets.token_urlsafe(32)
        key = self._key(token)
        payload = binding.model_dump_json()

        try:
            created = await self._redis.set(
                key,
                payload,
                ex=ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            raise AiToolGrantUnavailable(
                "AI tool grant authority is unavailable"
            ) from exc

        if created is not True:
            raise AiToolGrantUnavailable(
                "AI tool grant could not be issued safely"
            )

        return IssuedAiToolGrant(
            token=SecretStr(token),
            expires_in_seconds=ttl_seconds,
            binding=binding,
        )

    async def consume(
        self,
        *,
        token: str,
        capability: AiToolCapability,
        arguments: Mapping[str, Any],
        reason: str,
    ) -> AiToolGrantBinding:
        stored = await self._consume_stored_binding(
            token=token
        )
        tenant_query_context = await self._load_tenant_query_context(
            tenant_id=capability.tenant_id
        )
        expected = build_ai_tool_grant_binding(
            capability,
            tenant_query_context_fingerprint=(
                tenant_query_context.record_fingerprint
            ),
            arguments=arguments,
            reason=reason,
        )

        if stored != expected:
            raise AiToolGrantBindingMismatch(
                "AI tool grant binding does not match"
            )

        return stored

    async def consume_authorized_invocation(
        self,
        *,
        token: str,
        tool: str,
        arguments: Mapping[str, Any],
        reason: str,
    ) -> AuthorizedAiToolInvocation:
        """Consume without trusting caller identity or authority context claims."""

        if tool not in TOOL_REQUIRED_SCOPES:
            raise AiToolGrantInvalid(
                "AI tool is not supported"
            )

        query_policy = get_ai_query_contract_policy(tool)  # type: ignore[arg-type]
        arguments_sha256 = canonical_arguments_sha256(
            arguments
        )
        reason_sha256 = canonical_reason_sha256(reason)

        stored = await self._consume_stored_binding(
            token=token
        )

        _validate_scope_binding(
            tool=stored.tool,
            arguments=arguments,
            data_scope=stored.data_scope,
            data_scope_fingerprint=(
                stored.data_scope_fingerprint
            ),
        )

        # Deliberately after Redis GETDEL. If the tenant authority disappears,
        # changes, or becomes unavailable while a grant is outstanding, that
        # stale grant is burned and cannot be replayed after recovery.
        tenant_query_context = await self._load_tenant_query_context(
            tenant_id=stored.tenant_id
        )

        (
            current_query_contract_fingerprint,
            current_execution_scope_fingerprint,
        ) = _query_contract_binding(
            policy=query_policy,
            data_scope_fingerprint=(
                stored.data_scope_fingerprint
            ),
            tenant_query_context_fingerprint=(
                tenant_query_context.record_fingerprint
            ),
        )

        if (
            stored.tool != tool
            or stored.arguments_sha256 != arguments_sha256
            or stored.reason_sha256 != reason_sha256
            or stored.tenant_query_context_fingerprint
            != tenant_query_context.record_fingerprint
            or stored.query_contract_id != query_policy.contract_id
            or stored.query_contract_revision
            != query_policy.contract_revision
            or stored.query_contract_fingerprint
            != current_query_contract_fingerprint
            or stored.execution_scope_fingerprint
            != current_execution_scope_fingerprint
        ):
            raise AiToolGrantBindingMismatch(
                "AI tool grant binding does not match"
            )

        return AuthorizedAiToolInvocation(
            binding=stored,
            tenant_entity_ids=(
                tenant_query_context.context.entity_ids
            ),
        )
