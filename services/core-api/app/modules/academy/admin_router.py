from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.repository import (
    academy_admin_summary,
    list_admin_content,
    list_admin_paths,
)
from app.modules.academy.service import require_module

router = APIRouter(prefix="/admin", tags=["academy-admin"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
StudioUser = Annotated[
    Principal,
    Depends(require_permission("feature:academy:contentStudio")),
]


@router.get("/workspace")
async def get_authoring_workspace(
    session: TenantSession,
    principal: StudioUser,
) -> dict[str, object]:
    await require_module(session, principal)
    state = await academy_admin_summary(session, principal)
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "summary": state["summary"],
        "content": await list_admin_content(session, principal),
        "paths": await list_admin_paths(session, principal),
        "authoring": state["authoring"],
    }
