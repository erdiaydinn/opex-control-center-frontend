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
from app.core.authorization import has_control_plane_admin_authority, require_control_plane_admin
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
        "capabilities": {
            "control_plane_admin": await has_control_plane_admin_authority(principal),
        },
        "auth_mode": principal.auth_mode,
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
async def get_roles(
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, object]:
    roles = await list_tenant_roles(
        tenant_id=str(principal.tenant_id),
    )

    return {
        "tenant_id": str(principal.tenant_id),
        "items": roles,
    }


@app.get("/v1/admin/members", tags=["administration"])
async def get_members(
    principal: Principal = Depends(require_viewer),
) -> dict[str, object]:
    members = await list_tenant_members(
        tenant_id=str(principal.tenant_id),
    )

    return {
        "tenant_id": str(principal.tenant_id),
        "items": members,
    }


@app.post("/v1/admin/members", tags=["administration"])
async def create_member(
    payload: CreateTenantMemberRequest,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, object]:
    member = await create_tenant_member(
        tenant_id=str(principal.tenant_id),
        subject=payload.subject.strip(),
        email=payload.email.strip() if payload.email else None,
        display_name=payload.display_name.strip() if payload.display_name else None,
        roles=payload.roles,
    )

    return member


@app.patch("/v1/admin/members/{membership_id}", tags=["administration"])
async def patch_member(
    membership_id: UUID,
    payload: UpdateTenantMemberAccessRequest,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, object]:
    try:
        member = await update_tenant_member_access(
            tenant_id=str(principal.tenant_id),
            membership_id=str(membership_id),
            membership_status=payload.status,
            roles=payload.roles,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    return member


@app.get("/v1/platform/health", tags=["platform"])
async def platform_health(
    principal: Principal = Depends(require_control_plane_admin),
) -> dict[str, object]:
    del principal
    checks: dict[str, object] = {}

    async def timed_check(name: str, check) -> None:
        started = datetime.now(UTC)
        try:
            await check()
            elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            checks[name] = {"status": "ok", "latency_ms": elapsed_ms}
        except Exception as exc:
            checks[name] = {
                "status": "unavailable",
                "error_type": type(exc).__name__,
            }

    await asyncio.gather(
        timed_check("database", check_database),
        timed_check("redis", check_redis),
    )

    return {
        "status": "ok" if all(item["status"] == "ok" for item in checks.values()) else "degraded",
        "checks": checks,
    }


@app.get("/v1/platform/readiness", tags=["platform"])
async def platform_readiness(
    principal: Principal = Depends(require_control_plane_admin),
) -> dict[str, object]:
    del principal
    database_result, redis_result = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=True,
    )
    checks = {
        "database": "ok" if not isinstance(database_result, Exception) else "unavailable",
        "redis": "ok" if not isinstance(redis_result, Exception) else "unavailable",
    }
    return {
        "status": "ready" if all(value == "ok" for value in checks.values()) else "not_ready",
        "checks": checks,
    }


@app.get("/v1/platform/runtime", tags=["platform"])
async def platform_runtime(
    principal: Principal = Depends(require_control_plane_admin),
) -> dict[str, object]:
    del principal
    return {
        "environment": settings.environment,
        "auth_mode": settings.auth_mode,
        "database_driver": "postgresql+asyncpg",
        "redis_configured": bool(settings.redis_url),
    }


async def _proxy_budget(request: Request, suffix: str) -> JSONResponse:
    base_url = os.getenv("OPEX_BUDGET_INTERNAL_URL", "http://budget-api:8000").rstrip("/")
    url = f"{base_url}/v1/{suffix.lstrip('/')}"
    headers = {"X-Request-ID": request.state.request_id}
    authorization = request.headers.get("authorization")
    if authorization:
        headers["authorization"] = authorization

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method=request.method,
                url=url,
                params=request.query_params,
                content=await request.body(),
                headers=headers,
            )
    except httpx.HTTPError:
        return JSONResponse(status_code=503, content={"detail": "Budget service unavailable"})

    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": "Budget service returned invalid JSON"}

    return JSONResponse(status_code=response.status_code, content=payload)


@app.api_route(
    "/v1/budget/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    tags=["budget"],
)
async def budget_proxy(request: Request, path: str, principal: Principal = Depends(require_viewer)):
    del principal
    return await _proxy_budget(request, path)
