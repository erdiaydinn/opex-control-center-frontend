import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ai_tool_routes import router as ai_tool_router
from app.core.audit import build_audit_event
from app.core.authorization import require_control_plane_admin
from app.core.client_ip import resolve_client_ip
from app.core.config import get_settings
from app.core.resources import (
    check_database,
    check_redis,
    close_resources,
    create_tenant_member,
    get_tenant,
    list_audit_events,
    list_tenant_members,
    list_tenant_roles,
    update_tenant_display_name,
    update_tenant_member_access,
    write_audit_event,
)
from app.core.security import (
    Principal,
    require_platform_admin,
    require_super_admin,
    require_viewer,
)
from app.field_promotion_routes import router as field_promotion_router
from app.intelligence_routes import router as intelligence_router
from app.modules.academy.router import router as academy_router

settings = get_settings()

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class CreateTenantMemberRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    roles: list[str] = Field(min_length=1, max_length=4)


class UpdateTenantMemberAccessRequest(BaseModel):
    status: Literal["active", "suspended"]
    roles: list[str] = Field(min_length=1, max_length=4)


class UpdateTenantRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_resources()


app = FastAPI(
    title="OPEX Platform Core API",
    version="0.1.0",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.environment == "production" else "/openapi.json",
    lifespan=lifespan,
)

app.include_router(ai_tool_router)
app.include_router(intelligence_router)
app.include_router(field_promotion_router)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)


@app.middleware("http")
async def request_context_and_security_headers(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id if REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else str(uuid4())
    )
    request.state.request_id = request_id
    request.state.client_ip = resolve_client_ip(request)

    response = await call_next(request)

    principal = getattr(request.state, "principal", None)
    authenticated_principal = getattr(
        request.state,
        "authenticated_principal",
        None,
    )
    audit_principal = principal or authenticated_principal

    audit_event = build_audit_event(
        request_id=request_id,
        actor=getattr(audit_principal, "subject", None),
        tenant_id=(
            str(getattr(audit_principal, "tenant_id", "")) if audit_principal is not None else None
        ),
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        action=f"{request.method.lower()}:{request.url.path}",
        metadata={
            "client_host": getattr(
                request.state,
                "client_ip",
                None,
            ),
        },
    )

    if request.url.path not in {
        "/health/live",
        "/health/ready",
        "/v1/audit/events",
    }:
        print(
            json.dumps(
                {"event": "audit", **audit_event},
                ensure_ascii=False,
            ),
            flush=True,
        )

        try:
            await write_audit_event(audit_event)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "audit_write_failed",
                        "request_id": request_id,
                        "error_type": type(exc).__name__,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> JSONResponse:
    database_result, redis_result = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=True,
    )
    checks = {
        "database": "ok" if not isinstance(database_result, Exception) else "unavailable",
        "redis": "ok" if not isinstance(redis_result, Exception) else "unavailable",
    }
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@app.get("/v1/context", tags=["platform"])
async def current_context(
    request: Request,
    principal: Principal = Depends(require_viewer),
) -> dict[str, object]:
    return {
        "request_id": request.state.request_id,
        "actor": principal.subject,
        "tenant_id": principal.tenant_id,
        "roles": principal.roles,
        "permissions": principal.permissions,
        "permission_assignments": [
            assignment.model_dump() for assignment in principal.permission_assignments
        ],
        "auth_mode": principal.auth_mode,
    }


@app.get("/v1/platform/authority", tags=["platform"])
async def platform_authority(
    request: Request,
    principal: Principal = Depends(require_control_plane_admin),
) -> dict[str, object]:
    """Prove EAY control-plane authority without coupling access to service health."""
    return {
        "authorized": True,
        "request_id": request.state.request_id,
        "tenant_id": str(principal.tenant_id),
        "actor": principal.subject,
    }


@app.get("/v1/audit/events", tags=["platform"])
async def get_audit_events(
    principal: Principal = Depends(require_platform_admin),
    limit: int = 50,
    actor: str | None = None,
    decision: str | None = None,
    action: str | None = None,
) -> dict[str, object]:
    safe_limit = max(1, min(limit, 200))

    if decision not in {None, "allowed", "denied", "error"}:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "decision must be allowed, denied or error",
            },
        )

    items = await list_audit_events(
        tenant_id=str(principal.tenant_id),
        limit=safe_limit,
        actor=actor,
        decision=decision,
        action=action,
    )

    return {
        "tenant_id": str(principal.tenant_id),
        "count": len(items),
        "items": items,
    }


@app.patch("/v1/admin/tenant", tags=["administration"])
async def patch_current_tenant(
    payload: UpdateTenantRequest,
    principal: Principal = Depends(require_super_admin),
) -> dict[str, object]:
    display_name = payload.display_name.strip()

    if not display_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant display name cannot be empty",
        )

    tenant = await update_tenant_display_name(
        tenant_id=str(principal.tenant_id),
        display_name=display_name,
    )

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return tenant


@app.get("/v1/admin/tenant", tags=["administration"])
async def get_current_tenant(
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, object]:
    tenant = await get_tenant(
        tenant_id=str(principal.tenant_id),
    )

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return tenant


@app.get("/v1/admin/roles", tags=["administration"])
async def get_tenant_roles(
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, object]:
    items = await list_tenant_roles(
        tenant_id=str(principal.tenant_id),
    )

    return {
        "tenant_id": str(principal.tenant_id),
        "count": len(items),
        "items": items,
    }


@app.post(
    "/v1/admin/members",
    tags=["administration"],
    status_code=status.HTTP_201_CREATED,
)
async def post_tenant_member(
    payload: CreateTenantMemberRequest,
    principal: Principal = Depends(require_super_admin),
) -> dict[str, object]:
    try:
        return await create_tenant_member(
            tenant_id=str(principal.tenant_id),
            subject=payload.subject.strip(),
            email=payload.email.strip() if payload.email else None,
            display_name=(payload.display_name.strip() if payload.display_name else None),
            roles=tuple(payload.roles),
        )
    except ValueError as exc:
        detail = str(exc)

        if detail == "Membership already exists for this subject":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Membership already exists for this subject",
            ) from exc

        if detail.startswith("Unknown or non-system roles:"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role selection",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid membership request",
        ) from exc


@app.patch(
    "/v1/admin/members/{membership_id}",
    tags=["administration"],
)
async def patch_tenant_member_access(
    membership_id: UUID,
    payload: UpdateTenantMemberAccessRequest,
    principal: Principal = Depends(require_super_admin),
) -> dict[str, object]:
    try:
        return await update_tenant_member_access(
            tenant_id=str(principal.tenant_id),
            membership_id=str(membership_id),
            membership_status=payload.status,
            roles=tuple(payload.roles),
        )
    except ValueError as exc:
        detail = str(exc)

        if detail == "Membership not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            ) from exc

        if detail == "Cannot remove or suspend the last active super admin":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove or suspend the last active super admin",
            ) from exc

        if detail.startswith("Unknown or non-system roles:"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role selection",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid membership update",
        ) from exc


@app.get("/v1/admin/members", tags=["administration"])
async def get_tenant_members(
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, object]:
    items = await list_tenant_members(
        tenant_id=str(principal.tenant_id),
    )

    return {
        "tenant_id": str(principal.tenant_id),
        "count": len(items),
        "items": items,
    }


@app.get("/v1/platform/health", tags=["platform"])
async def platform_health(
    request: Request,
    principal: Principal = Depends(require_control_plane_admin),
) -> JSONResponse:
    async def check_platform_agent() -> dict[str, object]:
        agent_url = os.getenv(
            "PLATFORM_AGENT_URL",
            "http://platform-agent:8010",
        )

        async with httpx.AsyncClient(timeout=4.0) as client:
            container_response, backup_response = await asyncio.gather(
                client.get(f"{agent_url}/v1/containers"),
                client.get(f"{agent_url}/v1/backups/status"),
            )

            container_response.raise_for_status()
            backup_response.raise_for_status()

            return {
                "containers": container_response.json(),
                "backup": backup_response.json(),
            }

    database_result, redis_result, agent_result = await asyncio.gather(
        check_database(),
        check_redis(),
        check_platform_agent(),
        return_exceptions=True,
    )

    backup_warning_after_hours = float(os.getenv("OPEX_BACKUP_WARNING_AFTER_HOURS", "26"))
    backup_stale_after_hours = float(os.getenv("OPEX_BACKUP_STALE_AFTER_HOURS", "30"))

    backup_details: dict[str, object] = {}
    backup_status = "unavailable"
    backup_age_hours: float | None = None

    if not isinstance(agent_result, Exception):
        backup_details = dict(agent_result.get("backup", {}))
        recorded_status = backup_details.get("status")

        if recorded_status == "success":
            completed_at = backup_details.get("completed_at")

            if isinstance(completed_at, str):
                try:
                    completed_time = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))

                    if completed_time.tzinfo is None:
                        completed_time = completed_time.replace(tzinfo=UTC)

                    backup_age_hours = max(
                        0.0,
                        (datetime.now(UTC) - completed_time.astimezone(UTC)).total_seconds() / 3600,
                    )

                    if backup_age_hours > backup_stale_after_hours:
                        backup_status = "stale"
                    elif backup_age_hours > backup_warning_after_hours:
                        backup_status = "warning"
                    else:
                        backup_status = "ok"
                except ValueError:
                    backup_status = "unavailable"
        elif recorded_status == "failed":
            backup_status = "failed"

    backup_details.update(
        {
            "age_hours": (round(backup_age_hours, 2) if backup_age_hours is not None else None),
            "warning_after_hours": backup_warning_after_hours,
            "stale_after_hours": backup_stale_after_hours,
        }
    )

    checks = {
        "api": {
            "status": "ok",
            "version": app.version,
        },
        "database": {
            "status": ("ok" if not isinstance(database_result, Exception) else "unavailable"),
        },
        "redis": {
            "status": ("ok" if not isinstance(redis_result, Exception) else "unavailable"),
        },
        "containers": {
            "status": (
                agent_result.get("containers", {}).get("status", "unavailable")
                if not isinstance(agent_result, Exception)
                else "unavailable"
            ),
            "summary": (
                agent_result.get("containers", {}).get("summary", {})
                if not isinstance(agent_result, Exception)
                else {}
            ),
            "items": (
                agent_result.get("containers", {}).get("containers", [])
                if not isinstance(agent_result, Exception)
                else []
            ),
        },
        "backup": {
            "status": backup_status,
            "details": backup_details,
        },
    }

    healthy = all(item["status"] in {"ok", "healthy"} for item in checks.values())

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "degraded",
            "environment": settings.environment,
            "version": app.version,
            "request_id": request.state.request_id,
            "tenant_id": str(principal.tenant_id),
            "actor": principal.subject,
            "checks": checks,
        },
    )


app.include_router(academy_router)
