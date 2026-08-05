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


async def close_resources() -> None:
    await redis_client.aclose()
    await engine.dispose()
