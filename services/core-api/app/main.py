import asyncio
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.core.resources import check_database, check_redis, close_resources
from app.core.security import Principal, get_current_principal

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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    return {
        "request_id": request.state.request_id,
        "actor": principal.subject,
        "tenant_id": principal.tenant_id,
        "roles": principal.roles,
        "auth_mode": principal.auth_mode,
    }
