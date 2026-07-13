import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.dockos.router import router as dockos_router


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "OPEX_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="OPEX Control Center API",
    version="7.5.0-internal-test",
    docs_url="/api/docs" if os.getenv("DOCKOS_ENV", "development").lower() != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if os.getenv("DOCKOS_ENV", "development").lower() != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-OPEX-User", "X-OPEX-Role", "X-DockOS-Gateway"],
)

app.include_router(dockos_router, prefix="/api")


@app.get("/health", include_in_schema=False)
def root_health():
    return {"status": "ok", "service": "opex-control-center-backend", "release": "RC7.5"}
