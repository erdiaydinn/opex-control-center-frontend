from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def claim_idempotency_key(
    session: AsyncSession,
    principal: Principal,
    *,
    operation: str,
    idempotency_key: str | None,
    resource_id: str | None = None,
) -> tuple[UUID | None, dict[str, Any] | None]:
    if not idempotency_key:
        return None, None

    claim_id = await session.scalar(
        text(
            """
            INSERT INTO academy_idempotency_keys (
                tenant_id, subject, operation, idempotency_key, resource_id
            )
            VALUES (
                :tenant_id, :subject, :operation, :idempotency_key, :resource_id
            )
            ON CONFLICT (tenant_id, subject, operation, idempotency_key)
            DO NOTHING
            RETURNING id
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "subject": principal.subject,
            "operation": operation,
            "idempotency_key": idempotency_key,
            "resource_id": resource_id,
        },
    )
    if claim_id is not None:
        return claim_id, None

    existing = (
        await session.execute(
            text(
                """
                SELECT response
                FROM academy_idempotency_keys
                WHERE tenant_id = :tenant_id
                  AND subject = :subject
                  AND operation = :operation
                  AND idempotency_key = :idempotency_key
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "subject": principal.subject,
                "operation": operation,
                "idempotency_key": idempotency_key,
            },
        )
    ).mappings().one()
    response = existing["response"]
    return None, dict(response) if isinstance(response, dict) else response
