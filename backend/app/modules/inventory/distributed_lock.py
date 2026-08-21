from __future__ import annotations

import os
from functools import lru_cache

try:
    import redis
except ImportError:  # Local unit tests may run before requirements are installed.
    redis = None


class DistributedLockError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def client() -> redis.Redis | None:
    if redis is None:
        if os.getenv("DOCKOS_ENV", "development").lower() == "production":
            raise DistributedLockError("Production Redis bağımlılığı kurulu değil.")
        return None
    url = os.getenv("REDIS_URL", "")
    if not url:
        if os.getenv("DOCKOS_ENV", "development").lower() == "production":
            raise DistributedLockError("Production ortamında REDIS_URL zorunludur.")
        return None
    return redis.Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2,
        health_check_interval=20, retry_on_timeout=True,
    )


def claim(document_id: str, location: str, owner: str, ttl_seconds: int) -> bool:
    connection = client()
    if connection is None:
        return True
    key = f"inventory:lock:{document_id}:{location}"
    current = connection.get(key)
    if current == owner:
        connection.expire(key, ttl_seconds)
        return True
    return bool(connection.set(key, owner, nx=True, ex=ttl_seconds))


def owner(document_id: str, location: str) -> str | None:
    connection = client()
    return connection.get(f"inventory:lock:{document_id}:{location}") if connection else None


def ping() -> bool:
    connection = client()
    return bool(connection and connection.ping())
