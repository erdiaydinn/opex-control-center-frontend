"""OPEX provider-neutral Identity Gateway."""

from fastapi import FastAPI, Response

from app.security import (
    GatewaySettings,
    IdentitySigner,
)


settings = (
    GatewaySettings.from_environment()
)

signer = IdentitySigner(
    settings
)

app = FastAPI(
    title="OPEX Identity Gateway",
    version="0.1.0",
    docs_url=(
        None
        if settings.environment == "production"
        else "/docs"
    ),
    redoc_url=None,
    openapi_url=(
        None
        if settings.environment == "production"
        else "/openapi.json"
    ),
)


@app.middleware("http")
async def security_headers(
    request,
    call_next,
):
    response: Response = await call_next(
        request
    )

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return response


@app.get(
    "/health/live",
    include_in_schema=False,
)
async def liveness():
    return {
        "status": "ok",
    }


@app.get(
    "/health/ready",
    include_in_schema=False,
)
async def readiness():
    # Startup would already have failed if the
    # private signing key were unavailable.
    return {
        "status": "ok",
    }


@app.get(
    "/.well-known/jwks.json",
    include_in_schema=False,
)
async def jwks():
    return signer.public_jwks()


# Intentionally NO HTTP endpoint issues internal assertions.
#
# Authentication completion will call IdentitySigner only from
# trusted server-side code after provider verification,
# external-identity resolution and session establishment.
