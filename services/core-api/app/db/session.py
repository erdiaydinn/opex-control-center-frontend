from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.resources import engine
from app.core.security import Principal, get_current_principal

TenantSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def apply_tenant_context(session: AsyncSession, principal: Principal) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(principal.tenant_id)},
    )
    await session.execute(
        text("SELECT set_config('app.actor_subject', :actor_subject, true)"),
        {"actor_subject": principal.subject},
    )


async def get_tenant_session(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> AsyncIterator[AsyncSession]:
    async with TenantSessionFactory() as session, session.begin():
        await apply_tenant_context(session, principal)
        yield session
