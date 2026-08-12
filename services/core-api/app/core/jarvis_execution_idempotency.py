"""Durable, privacy-minimal idempotency for governed Jarvis execution.

PostgreSQL stores only tenant-scoped hashes, request fingerprint, state and
expiry. Raw Idempotency-Key, actor subject, tool arguments, human reason,
grant tokens and result rows are never persisted in this authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.ai_tool_authorization import AiToolCapability

JARVIS_IDEMPOTENCY_DEFAULT_TTL_SECONDS = 24 * 60 * 60
JARVIS_IDEMPOTENCY_MAX_TTL_SECONDS = 7 * 24 * 60 * 60
JARVIS_IDEMPOTENCY_VERSION = 1
JARVIS_IDEMPOTENCY_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"

IdempotencyState = Literal[
    "reserved",
    "dispatched",
    "completed",
    "indeterminate",
    "denied",
]


class JarvisIdempotencyError(RuntimeError):
    """Base durable idempotency authority failure."""


class JarvisIdempotencyInvalid(JarvisIdempotencyError):
    """Idempotency input is invalid."""


class JarvisIdempotencyConflict(JarvisIdempotencyError):
    """The same client key was used for a different governed request."""


class JarvisIdempotencyReplay(JarvisIdempotencyError):
    """The same governed request has already claimed this client key."""

    def __init__(self, state: IdempotencyState) -> None:
        super().__init__("Jarvis idempotency key has already been used")
        self.state = state


class JarvisIdempotencyUnavailable(JarvisIdempotencyError):
    """Durable idempotency authority is unavailable or inconsistent."""


class JarvisIdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = JARVIS_IDEMPOTENCY_VERSION
    request_fingerprint: str = Field(pattern=SHA256_PATTERN)
    state: IdempotencyState


def validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not JARVIS_IDEMPOTENCY_KEY_PATTERN.fullmatch(
        value
    ):
        raise JarvisIdempotencyInvalid(
            "Jarvis idempotency key is invalid"
        )
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def actor_subject_sha256(actor_subject: str) -> str:
    if not isinstance(actor_subject, str) or not actor_subject:
        raise JarvisIdempotencyInvalid("Jarvis actor subject is invalid")
    return _sha256_text(actor_subject)


def idempotency_key_sha256(idempotency_key: str) -> str:
    return _sha256_text(validate_idempotency_key(idempotency_key))


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JarvisIdempotencyInvalid(
            "Jarvis idempotency request cannot be canonicalized"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def build_execution_request_fingerprint(
    capability: AiToolCapability,
    *,
    arguments_sha256: str,
    reason_sha256: str,
    execution_policy: Mapping[str, Any],
) -> str:
    if not re.fullmatch(SHA256_PATTERN, arguments_sha256):
        raise JarvisIdempotencyInvalid("Arguments fingerprint is invalid")
    if not re.fullmatch(SHA256_PATTERN, reason_sha256):
        raise JarvisIdempotencyInvalid("Reason fingerprint is invalid")

    policy_sha256 = _canonical_json_sha256(execution_policy)
    return _canonical_json_sha256(
        {
            "tenant_id": str(capability.tenant_id),
            "actor_subject": capability.actor_subject,
            "tool": capability.tool,
            "arguments_sha256": arguments_sha256,
            "reason_sha256": reason_sha256,
            "authorization_fingerprint": (
                capability.authorization_fingerprint
            ),
            "execution_policy_sha256": policy_sha256,
        }
    )


class PostgresJarvisExecutionIdempotencyStore:
    """Reserve and transition one tenant-scoped execution key durably."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        ttl_seconds: int = JARVIS_IDEMPOTENCY_DEFAULT_TTL_SECONDS,
    ) -> None:
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 60 <= ttl_seconds <= JARVIS_IDEMPOTENCY_MAX_TTL_SECONDS
        ):
            raise ValueError("Jarvis idempotency TTL is invalid")
        self._engine = engine
        self._ttl_seconds = ttl_seconds

    @staticmethod
    async def _set_tenant(connection, tenant_id: UUID) -> None:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": str(tenant_id)},
        )

    def _values(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> dict[str, object]:
        if not re.fullmatch(SHA256_PATTERN, request_fingerprint):
            raise JarvisIdempotencyInvalid(
                "Jarvis request fingerprint is invalid"
            )
        return {
            "tenant_id": str(tenant_id),
            "actor_subject_sha256": actor_subject_sha256(actor_subject),
            "idempotency_key_sha256": idempotency_key_sha256(
                idempotency_key
            ),
            "request_fingerprint": request_fingerprint,
            "ttl_seconds": self._ttl_seconds,
        }

    async def reserve(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JarvisIdempotencyRecord:
        values = self._values(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        reserve_statement = text(
            """
            INSERT INTO jarvis_execution_idempotency (
                tenant_id,
                actor_subject_sha256,
                idempotency_key_sha256,
                request_fingerprint,
                state,
                expires_at
            ) VALUES (
                CAST(:tenant_id AS UUID),
                :actor_subject_sha256,
                :idempotency_key_sha256,
                :request_fingerprint,
                'reserved',
                CURRENT_TIMESTAMP
                    + CAST(:ttl_seconds AS INTEGER) * INTERVAL '1 second'
            )
            ON CONFLICT (
                tenant_id,
                actor_subject_sha256,
                idempotency_key_sha256
            )
            DO UPDATE SET
                request_fingerprint = EXCLUDED.request_fingerprint,
                state = 'reserved',
                expires_at = EXCLUDED.expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE jarvis_execution_idempotency.expires_at
                    <= CURRENT_TIMESTAMP
            RETURNING request_fingerprint, state
            """
        )
        inspect_statement = text(
            """
            SELECT request_fingerprint, state
            FROM jarvis_execution_idempotency
            WHERE tenant_id = CAST(:tenant_id AS UUID)
              AND actor_subject_sha256 = :actor_subject_sha256
              AND idempotency_key_sha256 = :idempotency_key_sha256
            """
        )

        try:
            async with self._engine.begin() as connection:
                await self._set_tenant(connection, tenant_id)
                result = await connection.execute(
                    reserve_statement,
                    values,
                )
                row = result.mappings().first()
                fresh_reservation = row is not None
                if row is None:
                    existing_result = await connection.execute(
                        inspect_statement,
                        values,
                    )
                    row = existing_result.mappings().first()
        except SQLAlchemyError as exc:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency authority is unavailable"
            ) from exc

        if row is None:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency reservation changed unexpectedly"
            )

        try:
            existing = JarvisIdempotencyRecord(
                request_fingerprint=str(row["request_fingerprint"]),
                state=str(row["state"]),
            )
        except ValueError as exc:
            raise JarvisIdempotencyUnavailable(
                "Stored Jarvis idempotency state is invalid"
            ) from exc

        if fresh_reservation:
            if existing.request_fingerprint != request_fingerprint:
                raise JarvisIdempotencyUnavailable(
                    "Fresh Jarvis idempotency fingerprint is inconsistent"
                )
            return existing

        if existing.request_fingerprint != request_fingerprint:
            raise JarvisIdempotencyConflict(
                "Jarvis idempotency key conflicts with another request"
            )
        raise JarvisIdempotencyReplay(existing.state)

    async def transition(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
        expected_state: IdempotencyState,
        new_state: IdempotencyState,
    ) -> JarvisIdempotencyRecord:
        values = self._values(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        values.update(
            {
                "expected_state": expected_state,
                "new_state": new_state,
            }
        )
        statement = text(
            """
            UPDATE jarvis_execution_idempotency
            SET
                state = :new_state,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = CAST(:tenant_id AS UUID)
              AND actor_subject_sha256 = :actor_subject_sha256
              AND idempotency_key_sha256 = :idempotency_key_sha256
              AND request_fingerprint = :request_fingerprint
              AND state = :expected_state
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING request_fingerprint, state
            """
        )

        try:
            async with self._engine.begin() as connection:
                await self._set_tenant(connection, tenant_id)
                result = await connection.execute(statement, values)
                row = result.mappings().first()
        except SQLAlchemyError as exc:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency transition is unavailable"
            ) from exc

        if row is None:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency state changed unexpectedly"
            )
        return JarvisIdempotencyRecord(
            request_fingerprint=str(row["request_fingerprint"]),
            state=str(row["state"]),
        )

    async def release_reserved(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> None:
        values = self._values(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        statement = text(
            """
            DELETE FROM jarvis_execution_idempotency
            WHERE tenant_id = CAST(:tenant_id AS UUID)
              AND actor_subject_sha256 = :actor_subject_sha256
              AND idempotency_key_sha256 = :idempotency_key_sha256
              AND request_fingerprint = :request_fingerprint
              AND state = 'reserved'
            RETURNING id
            """
        )

        try:
            async with self._engine.begin() as connection:
                await self._set_tenant(connection, tenant_id)
                result = await connection.execute(statement, values)
                deleted = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency release is unavailable"
            ) from exc

        if deleted is None:
            raise JarvisIdempotencyUnavailable(
                "Jarvis reserved idempotency state could not be released"
            )
