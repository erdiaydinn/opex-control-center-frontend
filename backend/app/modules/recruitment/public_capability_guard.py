"""Distributed abuse guard for anonymous recruitment capability endpoints."""
from __future__ import annotations

from hashlib import sha256
import hmac
import ipaddress
import os
from urllib.parse import urlparse

import redis
import redis.asyncio as aioredis
from fastapi import Request
from fastapi.responses import JSONResponse


class PublicCapabilityGuardError(RuntimeError):
    pass


PUBLIC_CAPABILITY_PATHS = {
    "/api/public/recruitment/offer": 60,
    "/api/public/recruitment/offer/decision": 12,
    "/api/public/recruitment/interview": 60,
    "/api/public/recruitment/interview/decision": 20,
    "/api/recruitment/candidate-upload/evidence": 12,
}
_WINDOW_SECONDS = 60
_MAX_CANDIDATE_UPLOAD_BYTES = 12 * 1024 * 1024


def _redis_url() -> str:
    return (
        os.getenv("RECRUITMENT_PUBLIC_CAPABILITY_REDIS_URL", "").strip()
        or os.getenv("REDIS_URL", "").strip()
    )


def _production() -> bool:
    return os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"


def preflight() -> dict:
    url = _redis_url()
    if not url:
        if _production():
            raise PublicCapabilityGuardError(
                "Production anonymous recruitment capability endpoints require Redis rate limiting."
            )
        return {"configured": False, "required": False}
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise PublicCapabilityGuardError("Recruitment public capability Redis URL is invalid.")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        client.close()
    except Exception as error:
        raise PublicCapabilityGuardError(
            "Recruitment public capability Redis authority is unavailable."
        ) from error
    return {
        "configured": True,
        "required": _production(),
        "tls": parsed.scheme == "rediss",
        "truth_boundary": "DISTRIBUTED_REDIS_FIXED_WINDOW_ABUSE_GUARD",
    }


def _trusted_proxy_client(request: Request) -> str | None:
    """Use proxy client IP only when the server-injected gateway secret proves origin."""
    configured = os.getenv("DOCKOS_GATEWAY_SECRET", "").strip()
    presented = request.headers.get("x-dockos-gateway", "").strip()
    if not configured or not presented or not hmac.compare_digest(configured, presented):
        return None
    forwarded = request.headers.get("x-real-ip", "").strip()
    if not forwarded:
        return None
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return None


def _source_key(request: Request) -> str:
    # nginx overwrites X-Real-IP and injects a server-side gateway secret. We only
    # trust that address when the secret matches; a directly exposed backend
    # therefore cannot be tricked with attacker-controlled forwarding headers.
    host = _trusted_proxy_client(request) or getattr(request.client, "host", None) or "unknown"
    return sha256(str(host).encode("utf-8")).hexdigest()[:24]


async def enforce(request: Request) -> JSONResponse | None:
    path = request.url.path
    limit = PUBLIC_CAPABILITY_PATHS.get(path)
    if limit is None:
        return None

    if path == "/api/recruitment/candidate-upload/evidence":
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > _MAX_CANDIDATE_UPLOAD_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Upload request is larger than the allowed public capability limit."},
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length."})

    url = _redis_url()
    if not url:
        if _production():
            return JSONResponse(status_code=503, content={"detail": "Public capability abuse guard unavailable."})
        return None

    source = _source_key(request)
    bucket = f"eay:recruitment:public-capability:{path}:{source}"
    try:
        client = aioredis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        async with client.pipeline(transaction=True) as pipe:
            pipe.incr(bucket)
            pipe.expire(bucket, _WINDOW_SECONDS, nx=True)
            count, _ = await pipe.execute()
        await client.aclose()
    except Exception:
        if _production():
            return JSONResponse(status_code=503, content={"detail": "Public capability abuse guard unavailable."})
        return None

    if int(count) > limit:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(_WINDOW_SECONDS)},
            content={"detail": "Too many capability requests. Try again shortly."},
        )
    return None
