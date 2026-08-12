import pytest_asyncio

from app.core.resources import engine


@pytest_asyncio.fixture(autouse=True)
async def dispose_application_engine_after_test():
    yield
    await engine.dispose()
