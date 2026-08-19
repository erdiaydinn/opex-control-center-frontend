from __future__ import annotations

import secrets

import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.core.jarvis_execution_admission import JarvisAdmissionLease
from app.core.resources import engine


class _RouteAdmissionStore:
    """Route-test authority; dedicated admission tests exercise Redis semantics."""

    def __init__(self) -> None:
        self.active: set[str] = set()

    async def acquire(self, *, tenant_id, actor_subject) -> JarvisAdmissionLease:
        assert tenant_id is not None
        assert actor_subject
        token = secrets.token_urlsafe(32)
        self.active.add(token)
        return JarvisAdmissionLease(
            token=SecretStr(token),
            lease_ttl_seconds=135,
        )

    async def release(self, lease: JarvisAdmissionLease) -> None:
        self.active.discard(lease.token.get_secret_value())


@pytest.fixture(autouse=True)
def isolate_jarvis_route_admission(monkeypatch: pytest.MonkeyPatch):
    """Prevent unrelated HTTP contract tests from depending on real Redis."""

    import app.ai_tool_routes as routes

    store = _RouteAdmissionStore()
    monkeypatch.setattr(routes, "_admission_store", store)
    return store


@pytest_asyncio.fixture(autouse=True)
async def dispose_application_engine_after_test():
    yield
    await engine.dispose()
