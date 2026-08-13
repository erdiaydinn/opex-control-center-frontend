from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def is_module_entitled(session: AsyncSession, tenant_id: UUID) -> bool:
    value = await session.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM tenant_entitlements
                WHERE tenant_id = :tenant_id
                  AND module_key = 'academy'
                  AND enabled = TRUE
                  AND (starts_at IS NULL OR starts_at <= CURRENT_TIMESTAMP)
                  AND (ends_at IS NULL OR ends_at > CURRENT_TIMESTAMP)
            )
            """
        ),
        {"tenant_id": tenant_id},
    )
    return bool(value)
