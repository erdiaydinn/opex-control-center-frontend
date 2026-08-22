from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from app.agent_job_repository import AgentJobRecord
from app.agent_job_routes import get_agent_job_repository
from app.core.security import Principal, get_current_principal
from app.main import app

TENANT_A = UUID("00000000-0000-4000-8000-0000000000a1")
TENANT_B = UUID("00000000-0000-4000-8000-0000000000b1")
NOW = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)


def principal(tenant_id=TENANT_A, *, allowed=True):
    return Principal(
        subject="user://erdi",
        tenant_id=tenant_id,
        roles=("viewer",),
        permissions=(("module:jarvis:view",) if allowed else ()),
        auth_mode="oidc",
    )


def record(tenant_id=TENANT_A, *, job_id=None, status="queued", epoch=0):
    return AgentJobRecord(
        id=job_id or uuid4(),
        tenant_id=tenant_id,
        requested_by="user://erdi",
        objective_ref="Research current market and operational risks",
        status=status,
        version=1 + epoch,
        cancellation_epoch=epoch,
        required_child_count=3,
        completed_child_count=0,
        effect_state="no_effect",
        created_at=NOW,
        updated_at=NOW,
        terminal_at=None,
    )


class FakeRepository:
    def __init__(self):
        self.item = record()
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        self.item = record(kwargs["tenant_id"])
        return self.item, True

    async def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        if kwargs["tenant_id"] == self.item.tenant_id and kwargs["job_id"] == self.item.id:
            return self.item
        return None

    async def events(self, **kwargs):
        self.calls.append(("events", kwargs))
        return ({"sequence": 1, "event_type": "created", "cancellation_epoch": 0},)

    async def cancel(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        if kwargs["tenant_id"] != self.item.tenant_id or kwargs["job_id"] != self.item.id:
            return None
        self.item = record(
            self.item.tenant_id,
            job_id=self.item.id,
            status="cancel_requested",
            epoch=1,
        )
        return self.item


@pytest.fixture
def fake():
    repository = FakeRepository()
    app.dependency_overrides[get_agent_job_repository] = lambda: repository
    yield repository
    app.dependency_overrides.clear()


async def request(method, path, current, **kwargs):
    async def override():
        return current
    app.dependency_overrides[get_current_principal] = override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        headers = {"Authorization": "Bearer test", **kwargs.pop("headers", {})}
        return await client.request(method, path, headers=headers, **kwargs)


@pytest.mark.asyncio
async def test_authenticated_create_derives_tenant_and_actor_from_principal(fake):
    response = await request(
        "POST", "/v1/ai/agent-jobs", principal(),
        headers={"Idempotency-Key": "hire-agents-0001"},
        json={
            "objective": "Research current market and operational risks",
            "requested_agent_count": 3,
        },
    )
    assert response.status_code == 202
    call = fake.calls[0][1]
    assert call["tenant_id"] == TENANT_A
    assert call["requested_by"] == "user://erdi"


@pytest.mark.asyncio
async def test_missing_jarvis_permission_is_denied_before_repository(fake):
    response = await request(
        "POST", "/v1/ai/agent-jobs", principal(allowed=False),
        headers={"Idempotency-Key": "hire-agents-0001"},
        json={"objective": "Research current market and operational risks"},
    )
    assert response.status_code == 403
    assert fake.calls == []


@pytest.mark.asyncio
async def test_cross_tenant_status_and_cancel_are_hidden_as_not_found(fake):
    job_id = fake.item.id
    status_response = await request("GET", f"/v1/ai/agent-jobs/{job_id}", principal(TENANT_B))
    cancel_response = await request(
        "POST", f"/v1/ai/agent-jobs/{job_id}/cancel", principal(TENANT_B)
    )
    assert status_response.status_code == 404
    assert cancel_response.status_code == 404
    assert all(call[1]["tenant_id"] == TENANT_B for call in fake.calls)


@pytest.mark.asyncio
async def test_events_are_bounded_and_cancel_increments_server_epoch(fake):
    job_id = fake.item.id
    event_response = await request(
        "GET", f"/v1/ai/agent-jobs/{job_id}/events?after_sequence=0&limit=25", principal()
    )
    cancel_response = await request("POST", f"/v1/ai/agent-jobs/{job_id}/cancel", principal())
    assert event_response.status_code == 200
    assert event_response.json()["events"][0]["event_type"] == "created"
    assert cancel_response.status_code == 202
    assert cancel_response.json()["cancellation_epoch"] == 1


def test_migration_has_force_rls_append_only_events_and_atomic_control_tables():
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/0051_jarvis_agent_control_plane.py"
    ).read_text()
    for table in (
        "jarvis_agent_jobs", "jarvis_agent_job_events", "jarvis_agent_budget_accounts",
        "jarvis_agent_budget_reservations", "jarvis_agent_commit_fences", "jarvis_agent_workers",
    ):
        assert table in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "REVOKE UPDATE ON TABLE jarvis_agent_job_events" in migration
    assert "UNIQUE (tenant_id, requested_by, idempotency_key)" in migration
