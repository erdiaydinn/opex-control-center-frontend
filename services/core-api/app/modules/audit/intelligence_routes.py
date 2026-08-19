from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.authorization import require_permission
from app.core.security import Principal

from .authorization import require_audit_scope
from .intelligence import build_audit_intelligence_receipt

router = APIRouter(prefix="/v1/audit/intelligence", tags=["audit-intelligence"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


@router.get("/summary")
async def get_audit_intelligence_summary(
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "feature:audit:analytics")
    return await build_audit_intelligence_receipt(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
    )
