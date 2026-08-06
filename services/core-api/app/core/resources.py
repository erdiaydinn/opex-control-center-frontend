from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)
redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis() -> None:
    if not await redis_client.ping():
        raise RuntimeError("Redis ping failed")


async def ensure_audit_table() -> None:
    statement = text(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL,
            request_id VARCHAR(128) NOT NULL,
            actor TEXT,
            tenant_id UUID,
            method VARCHAR(16) NOT NULL,
            path TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            action TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )

    async with engine.begin() as connection:
        await connection.execute(statement)


async def write_audit_event(event: dict[str, object]) -> None:
    import json

    tenant_id = event.get("tenant_id")
    actor = event.get("actor")

    if not tenant_id or not actor:
        return

    status_code = int(event.get("status_code", 500))

    if status_code < 400:
        decision = "allowed"
    elif status_code < 500:
        decision = "denied"
    else:
        decision = "error"

    statement = text(
        """
        INSERT INTO audit_events (
            tenant_id,
            actor_subject,
            action,
            resource_type,
            resource_id,
            decision,
            request_id,
            data
        )
        VALUES (
            CAST(:tenant_id AS UUID),
            :actor_subject,
            :action,
            :resource_type,
            :resource_id,
            :decision,
            :request_id,
            CAST(:data AS JSONB)
        )
        """
    )

    data = {
        "method": event.get("method"),
        "path": event.get("path"),
        "status_code": status_code,
        "occurred_at": event.get("occurred_at"),
        "metadata": event.get("metadata", {}),
    }

    values = {
        "tenant_id": str(tenant_id),
        "actor_subject": str(actor),
        "action": str(event.get("action", "unknown")),
        "resource_type": "http_request",
        "resource_id": None,
        "decision": decision,
        "request_id": str(event.get("request_id", "")),
        "data": json.dumps(data, ensure_ascii=False),
    }

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": str(tenant_id)},
        )
        await connection.execute(statement, values)


async def close_resources() -> None:
    await redis_client.aclose()
    await engine.dispose()
