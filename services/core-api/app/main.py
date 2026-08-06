import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.audit import build_audit_event
from app.core.config import get_settings
from app.core.resources import (
    check_database,
    check_redis,
    close_resources,
    write_audit_event,
    list_audit_events,
)
from app.core.security import Principal, require_platform_admin, require_viewer

settings = get_settings()
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


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
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else str(uuid4())
    )
    request.state.request_id = request_id

    response = await call_next(request)

    principal = getattr(request.state, "principal", None)

    audit_event = build_audit_event(
        request_id=request_id,
        actor=getattr(principal, "subject", None),
        tenant_id=(
            str(getattr(principal, "tenant_id", ""))
            if principal is not None
            else None
        ),
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        action=f"{request.method.lower()}:{request.url.path}",
        metadata={
            "client_host": (
                request.client.host
                if request.client is not None
                else None
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
                        "error": str(exc),
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

@app.get("/v1/platform/health", tags=["platform"])
async def platform_health(
    request: Request,
    principal: Principal = Depends(require_platform_admin),
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

    backup_warning_after_hours = float(
        os.getenv("OPEX_BACKUP_WARNING_AFTER_HOURS", "26")
    )
    backup_stale_after_hours = float(
        os.getenv("OPEX_BACKUP_STALE_AFTER_HOURS", "30")
    )

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
                    completed_time = datetime.fromisoformat(
                        completed_at.replace("Z", "+00:00")
                    )

                    if completed_time.tzinfo is None:
                        completed_time = completed_time.replace(
                            tzinfo=timezone.utc
                        )

                    backup_age_hours = max(
                        0.0,
                        (
                            datetime.now(timezone.utc)
                            - completed_time.astimezone(timezone.utc)
                        ).total_seconds()
                        / 3600,
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
            "age_hours": (
                round(backup_age_hours, 2)
                if backup_age_hours is not None
                else None
            ),
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
            "status": (
                "ok"
                if not isinstance(database_result, Exception)
                else "unavailable"
            ),
        },
        "redis": {
            "status": (
                "ok"
                if not isinstance(redis_result, Exception)
                else "unavailable"
            ),
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

    healthy = all(
        item["status"] in {"ok", "healthy"}
        for item in checks.values()
    )

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
