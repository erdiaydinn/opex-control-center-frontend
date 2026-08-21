import logging
import os
import time
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, make_asgi_app

from app.modules.dockos import router as dockos_router_module
from app.modules.dockos import service as dockos_service
from app.modules.dockos.identity import authenticate_request as authenticate_dockos_request, reset_identity as reset_dockos_identity, set_identity as set_dockos_identity, verify_gateway as verify_dockos_gateway
from app.modules.dockos.observability import record_reservation, render_prometheus as render_dockos_prometheus, snapshot as dockos_snapshot
from app.modules.dockos.persistence import persistence_mode as dockos_persistence_mode, refresh_state as refresh_dockos_state
from app.modules.dockos.production_runtime import install_service_security as install_dockos_service_security, readiness_checks as dockos_readiness_checks, sync_bigquery_purchase_orders as sync_dockos_bigquery_purchase_orders
from app.modules.dockos.router import router as dockos_router
from app.modules.dockos.runtime_db import pool as dockos_db_pool
from app.modules.identity.router import router as identity_router
from app.modules.identity.service import bootstrap_admin, initialize as initialize_identity
from app.modules.inventory.router import router as inventory_router
from app.modules.inventory.service import initialize as initialize_inventory
from app.modules.recruitment.interview_router import public_router as recruitment_public_interview_router, router as recruitment_interview_router
from app.modules.recruitment.lifecycle_governance_router import router as recruitment_lifecycle_governance_router
from app.modules.recruitment.lifecycle_router import router as recruitment_lifecycle_router
from app.modules.recruitment.onboarding_router import router as recruitment_onboarding_router
from app.modules.recruitment.orchestration_router import public_router as recruitment_public_orchestration_router, router as recruitment_orchestration_router
from app.modules.recruitment.production_evidence_router import router as recruitment_production_evidence_router
from app.modules.recruitment.production_startup_guard import assert_recruitment_production_ready
from app.modules.recruitment.public_capability_guard import enforce as enforce_public_capability_guard
from app.modules.recruitment.router import router as recruitment_router
from app.modules.recruitment.scanner_callback_router import router as recruitment_scanner_callback_router
from app.modules.recruitment.service import initialize as initialize_recruitment
from app.modules.workforce.capacity_router import router as workforce_capacity_router
from app.modules.workforce.flexibility_router import router as workforce_flexibility_router
from app.modules.workforce.router import router as workforce_router
from app.modules.workforce.service import WorkforceRuleError, initialize_workforce
from app.modules.workforce.timeoff_router import router as workforce_timeoff_router
from app.security import WorkforceIdentityMiddleware


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("opex.api")
REQUEST_COUNT = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])
DOCKOS_PRODUCTION = os.getenv("DOCKOS_ENV", "development").lower() == "production"

if os.getenv("SENTRY_DSN"):
    import sentry_sdk
    sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], environment=os.getenv("DOCKOS_ENV", "development"), traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")), send_default_pii=False)

if DOCKOS_PRODUCTION:
    install_dockos_service_security(dockos_service)
    dockos_router_module.is_admin = dockos_service.is_admin

    def _production_live_pos(supplier_name=None, warehouse_name=None, user_email=None, user_role=None):
        if supplier_name:
            dockos_service.assert_supplier_access(user_email, supplier_name, user_role)
        return sync_dockos_bigquery_purchase_orders(dockos_service, supplier_name, warehouse_name)

    dockos_router_module.get_live_purchase_orders = _production_live_pos
    dockos_service.get_live_purchase_orders = _production_live_pos


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_workforce()
    assert_recruitment_production_ready()
    initialize_recruitment()
    initialize_inventory()
    initialize_identity()
    bootstrap_admin()
    LOGGER.info("platform persistence initialized")
    yield


def _cors_origins() -> list[str]:
    raw = os.getenv("OPEX_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _dockos_pool_stats() -> dict:
    if dockos_persistence_mode() != "postgres":
        return {}
    try:
        return dockos_db_pool().get_stats()
    except Exception:
        return {}


def _replace_verified_dockos_headers(request: Request, email: str, role: str) -> None:
    blocked = {b"x-opex-user", b"x-opex-role", b"x-dockos-gateway"}
    headers = [(key, value) for key, value in request.scope["headers"] if key not in blocked]
    headers.extend([(b"x-opex-user", email.encode("utf-8")), (b"x-opex-role", role.encode("utf-8")), (b"x-dockos-gateway", os.environ["DOCKOS_GATEWAY_SECRET"].encode("utf-8"))])
    request.scope["headers"] = headers


def _production_permissions_policy(path: str) -> str:
    if path.startswith("/api/field-intelligence"):
        return "camera=(self), microphone=(), geolocation=(self)"
    if path.startswith("/api/workforce"):
        return "camera=(), microphone=(), geolocation=(self)"
    return "camera=(), microphone=(), geolocation=()"


app = FastAPI(title="EAY Platform API", version="26.6.0-converged", docs_url="/api/docs" if not DOCKOS_PRODUCTION else None, redoc_url=None, openapi_url="/api/openapi.json" if not DOCKOS_PRODUCTION else None, lifespan=lifespan)
app.add_middleware(WorkforceIdentityMiddleware)


@app.exception_handler(WorkforceRuleError)
async def workforce_conflict_handler(_: Request, error: WorkforceRuleError):
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})


app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID", "X-EAY-Upload-Capability", "X-DockOS-Gateway-Timestamp", "X-DockOS-Gateway-Nonce", "X-DockOS-Gateway-Signature"])


@app.middleware("http")
async def dockos_production_boundary(request: Request, call_next):
    path = request.url.path
    started = time.perf_counter()
    status_code = 500
    identity_token = None

    guard_response = await enforce_public_capability_guard(request)
    if guard_response is not None:
        return guard_response

    if DOCKOS_PRODUCTION and path == "/api/dockos/readiness":
        try:
            if dockos_persistence_mode() == "postgres":
                refresh_dockos_state()
            checks = dockos_readiness_checks(dockos_service)
            slo = dockos_snapshot(dockos_service, _dockos_pool_stats())
            status_code = 200 if all(item["ok"] for item in checks) else 503
            return JSONResponse({"ready": status_code == 200, "release": "EAY-converged-production-candidate", "checks": checks, "slo": slo}, status_code=status_code)
        except Exception as error:
            return JSONResponse({"ready": False, "release": "EAY-converged-production-candidate", "checks": [{"key": "readiness", "ok": False, "detail": str(error)[:300]}]}, status_code=503)
    protected = path.startswith("/api/dockos") and not path.endswith("/health")
    try:
        if DOCKOS_PRODUCTION and protected:
            verify_dockos_gateway(request)
            identity = authenticate_dockos_request(request)
            identity_token = set_dockos_identity(identity)
            _replace_verified_dockos_headers(request, identity.email, identity.role)
            refresh_dockos_state()
        elif dockos_persistence_mode() == "postgres" and path.startswith("/api/dockos"):
            refresh_dockos_state()
        response = await call_next(request)
        status_code = response.status_code
        if DOCKOS_PRODUCTION:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = _production_permissions_policy(path)
            response.headers["X-Frame-Options"] = "DENY"
            if path.startswith("/api/recruitment") or path.startswith("/api/public/recruitment"):
                response.headers["Cache-Control"] = "no-store, private"
        return response
    except HTTPException as error:
        status_code = error.status_code
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)
    except PermissionError as error:
        status_code = 403
        return JSONResponse({"detail": str(error)}, status_code=403)
    except ValueError as error:
        status_code = 400
        return JSONResponse({"detail": str(error)}, status_code=400)
    except RuntimeError as error:
        status_code = 503
        return JSONResponse({"detail": str(error)}, status_code=503)
    finally:
        if identity_token is not None:
            reset_dockos_identity(identity_token)
        if request.method.upper() == "POST" and path == "/api/dockos/reservations":
            record_reservation((time.perf_counter() - started) * 1000.0, status_code < 400)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("x-request-id", "").strip()
    request_id = supplied_request_id if supplied_request_id and len(supplied_request_id) <= 96 and supplied_request_id.replace("-", "").replace("_", "").isalnum() else str(uuid4())
    started = perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    REQUEST_COUNT.labels(request.method, route_path, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(request.method, route_path).observe(perf_counter() - started)
    response.headers["X-Request-ID"] = request_id
    LOGGER.info("request method=%s path=%s status=%s request_id=%s", request.method, request.url.path, response.status_code, request_id)
    return response


@app.get("/api/dockos/ops/metrics", include_in_schema=False)
def dockos_metrics():
    return PlainTextResponse(render_dockos_prometheus(dockos_snapshot(dockos_service, _dockos_pool_stats())), media_type="text/plain; version=0.0.4")


app.include_router(dockos_router, prefix="/api")
app.include_router(workforce_router, prefix="/api")
app.include_router(workforce_capacity_router, prefix="/api")
app.include_router(workforce_flexibility_router, prefix="/api")
app.include_router(workforce_timeoff_router, prefix="/api")
# Capability-only candidate routes sit outside employee SSO and never receive bearer identity.
app.include_router(recruitment_public_orchestration_router, prefix="/api")
app.include_router(recruitment_public_interview_router, prefix="/api")
app.include_router(recruitment_scanner_callback_router, prefix="/api")
app.include_router(recruitment_production_evidence_router, prefix="/api")
app.include_router(recruitment_interview_router, prefix="/api")
app.include_router(recruitment_onboarding_router, prefix="/api")
# Governance shadows generic lifecycle mutations for owner/waiver/close separation.
app.include_router(recruitment_lifecycle_governance_router, prefix="/api")
# V47 lifecycle precedes orchestration so offers cannot bypass four-eyes approval.
app.include_router(recruitment_lifecycle_router, prefix="/api")
# Orchestration precedes legacy recruitment so hire activation is fail-closed on readiness.
app.include_router(recruitment_orchestration_router, prefix="/api")
app.include_router(recruitment_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(identity_router, prefix="/api")
app.mount("/metrics", make_asgi_app())


@app.get("/health", include_in_schema=False)
def root_health():
    return {"status": "ok", "service": "eay-platform-backend", "release": "convergence-v0.1", "dockos_persistence": dockos_persistence_mode()}
