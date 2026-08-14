from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def claim_idempotency_key(
    session: AsyncSession,
    principal: Principal,
    *,
    operation: str,
    idempotency_key: str | None,
    request_fingerprint: str,
    resource_id: str | None = None,
) -> dict[str, Any]:
    if not idempotency_key:
        return {"claimed": True, "claim_id": None, "resource_id": resource_id}

    claim_id = await session.scalar(
        text(
            """
            INSERT INTO academy_idempotency_keys (
                tenant_id, subject, operation, idempotency_key, resource_id, request_fingerprint
            ) VALUES (
                :tenant_id, :subject, :operation, :idempotency_key, :resource_id,
                :request_fingerprint
            )
            ON CONFLICT (tenant_id, subject, operation, idempotency_key) DO NOTHING
            RETURNING id
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "subject": principal.subject,
            "operation": operation,
            "idempotency_key": idempotency_key,
            "resource_id": resource_id,
            "request_fingerprint": request_fingerprint,
        },
    )
    if claim_id is not None:
        return {"claimed": True, "claim_id": claim_id, "resource_id": resource_id}

    existing = (
        (
            await session.execute(
                text(
                    """
                SELECT resource_id, request_fingerprint
                FROM academy_idempotency_keys
                WHERE tenant_id = :tenant_id AND subject = :subject
                  AND operation = :operation AND idempotency_key = :idempotency_key
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                    "operation": operation,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        .mappings()
        .one()
    )
    return {
        "claimed": False,
        "claim_id": None,
        "resource_id": existing["resource_id"],
        "request_fingerprint": existing["request_fingerprint"],
    }
