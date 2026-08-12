"""Single-use execution grants for authorized Jarvis tool calls.

A capability answers *what* an actor may do and *which data* it may touch. A
tool grant binds that capability to exactly one concrete invocation and can be
consumed once. Raw grant tokens, tool arguments and human reasons are never
stored in Redis. The short-lived trusted data scope is stored because the
consumer must recover it without trusting caller-supplied authorization data.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.ai_data_scope import AiDataScope
from app.core.ai_tool_authorization import (
    TOOL_REQUIRED_SCOPES,
    AiToolCapability,
    AiToolName,
)

AI_TOOL_GRANT_DEFAULT_TTL_SECONDS = 30
AI_TOOL_GRANT_MAX_TTL_SECONDS = 60
AI_TOOL_GRANT_VERSION = 2
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class AiToolGrantError(PermissionError):
    """Base denial for Jarvis single-use execution grants."""


class AiToolGrantInvalid(AiToolGrantError):
    """The invocation cannot be represented by the grant contract."""


class AiToolGrantUnavailable(AiToolGrantError):
    """The distributed grant authority is unavailable."""


class AiToolGrantReplayOrExpired(AiToolGrantError):
    """The opaque grant has already been consumed or has expired."""


class AiToolGrantBindingMismatch(AiToolGrantError):
    """The grant was issued for a different invocation."""


class AiToolGrantBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal[2] = AI_TOOL_GRANT_VERSION
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


def build_ai_tool_grant_binding(
    capability: AiToolCapability,
    *,
    arguments: Mapping[str, Any],
    reason: str,
) -> AiToolGrantBinding:
    return AiToolGrantBinding(
        tenant_id=capability.tenant_id,
        actor_subject=capability.actor_subject,
        tool=capability.tool,
        data_scope=capability.data_scope,
        data_scope_fingerprint=(
            capability.data_scope_fingerprint
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

        binding = build_ai_tool_grant_binding(
            capability,
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
        expected = build_ai_tool_grant_binding(
            capability,
            arguments=arguments,
            reason=reason,
        )
        stored = await self._consume_stored_binding(
            token=token
        )

        # GETDEL happens before comparison on purpose. A mismatched attempt
        # burns the grant instead of leaving a usable bearer capability.
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
    ) -> AiToolGrantBinding:
        """Consume a Core-issued grant without trusting caller identity.

        Tenant, actor, authorization fingerprint and data scope are recovered
        only from the short-lived Redis record written during the authenticated
        issue flow. Jarvis can prove possession of the opaque token and must
        reproduce the exact invocation, but cannot choose authorization data.
        """

        if tool not in TOOL_REQUIRED_SCOPES:
            raise AiToolGrantInvalid(
                "AI tool is not supported"
            )

        arguments_sha256 = canonical_arguments_sha256(
            arguments
        )
        reason_sha256 = canonical_reason_sha256(reason)

        stored = await self._consume_stored_binding(
            token=token
        )

        if (
            stored.tool != tool
            or stored.arguments_sha256
            != arguments_sha256
            or stored.reason_sha256
            != reason_sha256
        ):
            raise AiToolGrantBindingMismatch(
                "AI tool grant binding does not match"
            )

        return stored
