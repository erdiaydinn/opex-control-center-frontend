"""Tenant-scoped authority for downstream Jarvis query discriminators."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.resources import engine

QUERY_CONTEXT_VERSION = 1
MAX_ENTITY_IDS = 16
MAX_ENTITY_ID_LENGTH = 64
ABSENT_QUERY_CONTEXT_FINGERPRINT = hashlib.sha256(
    b'{"state":"absent"}'
).hexdigest()

_BLOCKED_ENTITY_IDS = frozenset(
    {
        "*",
        "all",
        "all_entities",
        "__all__",
    }
)


class AiTenantQueryContextError(RuntimeError):
    """Base query-context authority failure."""


class AiTenantQueryContextInvalid(AiTenantQueryContextError):
    """The discriminator context is malformed or unsafe."""


class AiTenantQueryContextConflict(AiTenantQueryContextError):
    """The tenant query context changed since it was read."""


class AiTenantQueryContext(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    version: Literal[1]
    entity_ids: tuple[str, ...]
    source_reference: str

    @field_validator("entity_ids", mode="before")
    @classmethod
    def validate_entity_ids(cls, value: Any) -> tuple[str, ...]:
        if (
            not isinstance(value, (list, tuple))
            or isinstance(value, (str, bytes, bytearray))
            or not 1 <= len(value) <= MAX_ENTITY_IDS
        ):
            raise ValueError(
                "entity_ids must be a bounded non-empty list"
            )

        normalized: list[str] = []
        seen: dict[str, str] = {}

        for raw in value:
            if not isinstance(raw, str):
                raise ValueError("entity_id must be text")

            entity_id = unicodedata.normalize(
                "NFC",
                raw.strip(),
            )
            if (
                not entity_id
                or len(entity_id) > MAX_ENTITY_ID_LENGTH
                or entity_id.casefold() in _BLOCKED_ENTITY_IDS
                or "*" in entity_id
                or "%" in entity_id
                or any(char.isspace() for char in entity_id)
            ):
                raise ValueError("entity_id is unsafe")

            key = entity_id.casefold()
            previous = seen.get(key)
            if previous is not None:
                raise ValueError(
                    "entity_ids contain duplicate or case-ambiguous values"
                )

            seen[key] = entity_id
            normalized.append(entity_id)

        return tuple(
            sorted(
                normalized,
                key=lambda item: (
                    item.casefold(),
                    item,
                ),
            )
        )

    @field_validator("source_reference", mode="before")
    @classmethod
    def validate_source_reference(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("source_reference must be text")

        normalized = " ".join(value.split())
        if not 3 <= len(normalized) <= 512:
            raise ValueError("source_reference length is invalid")

        return normalized


@dataclass(frozen=True)
class AiTenantQueryContextRecord:
    tenant_id: str
    context: AiTenantQueryContext
    record_fingerprint: str
    updated_by: str


@dataclass(frozen=True)
class AiTenantQueryContextUpdate:
    tenant_id: str
    context: AiTenantQueryContext
    record_fingerprint: str
    changed: bool


def ai_tenant_query_context_fingerprint(
    context: AiTenantQueryContext,
) -> str:
    encoded = json.dumps(
        context.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_reference_sha256(source_reference: str) -> str:
    return hashlib.sha256(
        source_reference.encode("utf-8")
    ).hexdigest()


async def get_ai_tenant_query_context(
    *,
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    statement = text(
        """
        SELECT
            context_version,
            entity_ids,
            source_reference,
            updated_by
        FROM ai_tenant_query_contexts
        WHERE tenant_id = CAST(:tenant_id AS UUID)
        """
    )

    async with engine.begin() as connection:
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
            {"tenant_id": tenant_id},
        )
        result = await connection.execute(
            statement,
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()

    if row is None:
        return None

    try:
        context = AiTenantQueryContext(
            version=int(row["context_version"]),
            entity_ids=tuple(row["entity_ids"]),
            source_reference=str(row["source_reference"]),
        )
    except (ValueError, TypeError) as exc:
        raise AiTenantQueryContextInvalid(
            "Persisted tenant query context is invalid"
        ) from exc

    return AiTenantQueryContextRecord(
        tenant_id=tenant_id,
        context=context,
        record_fingerprint=(
            ai_tenant_query_context_fingerprint(context)
        ),
        updated_by=str(row["updated_by"]),
    )


async def _write_query_context_audit_in_transaction(
    connection: AsyncConnection,
    *,
    tenant_id: str,
    actor_subject: str,
    request_id: str,
    old_record_fingerprint: str,
    new_record_fingerprint: str,
    old_entity_count: int,
    new_entity_count: int,
    source_reference_sha256: str,
) -> None:
    data = {
        "method": "PUT",
        "path": "/v1/admin/ai-query-context",
        "status_code": 200,
        "metadata": {
            "old_record_fingerprint": old_record_fingerprint,
            "new_record_fingerprint": new_record_fingerprint,
            "old_entity_count": old_entity_count,
            "new_entity_count": new_entity_count,
            "source_reference_sha256": source_reference_sha256,
        },
    }

    await connection.execute(
        text(
            """
            INSERT INTO audit_events (
                tenant_id,
                actor_subject,
                action,
                resource_type,
                resource_id,
                decision,
                request_id,
                data
            )
            VALUES (
                CAST(:tenant_id AS UUID),
                :actor_subject,
                'ai_tenant_query_context_changed',
                'tenant_query_context',
                :tenant_id,
                'allowed',
                :request_id,
                CAST(:data AS JSONB)
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "actor_subject": actor_subject,
            "request_id": request_id,
            "data": json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    )


async def put_ai_tenant_query_context(
    *,
    tenant_id: str,
    expected_record_fingerprint: str,
    context: AiTenantQueryContext,
    actor_subject: str,
    request_id: str,
) -> AiTenantQueryContextUpdate:
    if (
        len(expected_record_fingerprint) != 64
        or any(
            char not in "0123456789abcdef"
            for char in expected_record_fingerprint
        )
    ):
        raise ValueError(
            "expected_record_fingerprint must be lowercase SHA-256"
        )

    new_record_fingerprint = (
        ai_tenant_query_context_fingerprint(context)
    )

    async with engine.begin() as connection:
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
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            text(
                """
                SELECT
                    context_version,
                    entity_ids,
                    source_reference,
                    updated_by
                FROM ai_tenant_query_contexts
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()

        if row is None:
            if (
                expected_record_fingerprint
                != ABSENT_QUERY_CONTEXT_FINGERPRINT
            ):
                raise AiTenantQueryContextConflict(
                    "Tenant query context changed"
                )

            insert_result = await connection.execute(
                text(
                    """
                    INSERT INTO ai_tenant_query_contexts (
                        tenant_id,
                        context_version,
                        entity_ids,
                        source_reference,
                        updated_by
                    )
                    VALUES (
                        CAST(:tenant_id AS UUID),
                        :context_version,
                        CAST(:entity_ids AS JSONB),
                        :source_reference,
                        :updated_by
                    )
                    ON CONFLICT (tenant_id) DO NOTHING
                    RETURNING tenant_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "context_version": context.version,
                    "entity_ids": json.dumps(
                        list(context.entity_ids),
                        ensure_ascii=False,
                    ),
                    "source_reference": context.source_reference,
                    "updated_by": actor_subject,
                },
            )
            if insert_result.scalar_one_or_none() is None:
                # Only a genuine concurrent first writer maps to a refreshable
                # CAS conflict. DB, permission and audit failures remain 5xx.
                raise AiTenantQueryContextConflict(
                    "Tenant query context changed"
                )

            old_record_fingerprint = (
                ABSENT_QUERY_CONTEXT_FINGERPRINT
            )
            old_entity_count = 0
        else:
            try:
                old_context = AiTenantQueryContext(
                    version=int(row["context_version"]),
                    entity_ids=tuple(row["entity_ids"]),
                    source_reference=str(row["source_reference"]),
                )
            except (ValueError, TypeError) as exc:
                raise AiTenantQueryContextInvalid(
                    "Persisted tenant query context is invalid"
                ) from exc

            old_record_fingerprint = (
                ai_tenant_query_context_fingerprint(old_context)
            )
            old_entity_count = len(old_context.entity_ids)

            if old_record_fingerprint != expected_record_fingerprint:
                raise AiTenantQueryContextConflict(
                    "Tenant query context changed"
                )

            if old_record_fingerprint == new_record_fingerprint:
                return AiTenantQueryContextUpdate(
                    tenant_id=tenant_id,
                    context=context,
                    record_fingerprint=new_record_fingerprint,
                    changed=False,
                )

            await connection.execute(
                text(
                    """
                    UPDATE ai_tenant_query_contexts
                    SET
                        context_version = :context_version,
                        entity_ids = CAST(:entity_ids AS JSONB),
                        source_reference = :source_reference,
                        updated_by = :updated_by,
                        updated_at = NOW()
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "context_version": context.version,
                    "entity_ids": json.dumps(
                        list(context.entity_ids),
                        ensure_ascii=False,
                    ),
                    "source_reference": context.source_reference,
                    "updated_by": actor_subject,
                },
            )

        await _write_query_context_audit_in_transaction(
            connection,
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            request_id=request_id,
            old_record_fingerprint=old_record_fingerprint,
            new_record_fingerprint=new_record_fingerprint,
            old_entity_count=old_entity_count,
            new_entity_count=len(context.entity_ids),
            source_reference_sha256=(
                _source_reference_sha256(
                    context.source_reference
                )
            ),
        )

    return AiTenantQueryContextUpdate(
        tenant_id=tenant_id,
        context=context,
        record_fingerprint=new_record_fingerprint,
        changed=True,
    )
