import os
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app

from app.modules.dockos.router import router as dockos_router
from app.modules.workforce.router import router as workforce_router
from app.modules.workforce.service import initialize_workforce
from app.modules.recruitment.router import router as recruitment_router
from app.modules.recruitment.service import initialize as initialize_recruitment
from app.modules.inventory.router import router as inventory_router
from app.modules.inventory.service import initialize as initialize_inventory
from app.security import WorkforceIdentityMiddleware
from app.modules.identity.router import router as identity_router
from app.modules.identity.service import bootstrap_admin, initialize as initialize_identity


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("opex.api")
REQUEST_COUNT = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])
if os.getenv("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.getenv("DOCKOS_ENV", "development"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_workforce()
    initialize_recruitment()
    initialize_inventory()
    initialize_identity()
    bootstrap_admin()
    LOGGER.info("workforce persistence initialized")
    yield


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "OPEX_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="OPEX Control Center API",
    version="26.6.0",
    docs_url="/api/docs" if os.getenv("DOCKOS_ENV", "development").lower() != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if os.getenv("DOCKOS_ENV", "development").lower() != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(WorkforceIdentityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID", "X-DockOS-Gateway"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    started = perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    REQUEST_COUNT.labels(request.method, route_path, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(request.method, route_path).observe(perf_counter() - started)
    response.headers["X-Request-ID"] = request_id
    LOGGER.info("request method=%s path=%s status=%s request_id=%s", request.method, request.url.path, response.status_code, request_id)
    return response

app.include_router(dockos_router, prefix="/api")
app.include_router(workforce_router, prefix="/api")
app.include_router(recruitment_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(identity_router, prefix="/api")
app.mount("/metrics", make_asgi_app())


@app.get("/health", include_in_schema=False)
def root_health():
    return {"status": "ok", "service": "opex-control-center-backend", "release": "Unified-V26.6"}
