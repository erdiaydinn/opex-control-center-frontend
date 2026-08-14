import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.resources import engine

TENANT = UUID("00000000-0000-0000-0000-00000000c001")
CONTENT = UUID("00000000-0000-0000-0000-00000000c002")
VERSION = UUID("00000000-0000-0000-0000-00000000c003")
PATH = UUID("00000000-0000-0000-0000-00000000c004")
ENROLLMENT = UUID("00000000-0000-0000-0000-00000000c005")
PROGRESS = UUID("00000000-0000-0000-0000-00000000c006")
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def tenant_context(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": str(TENANT)})


@pytest.mark.asyncio
async def test_progress_optimistic_revision_allows_only_one_concurrent_writer() -> None:
    async with Session() as s, s.begin():
        await tenant_context(s)
        await s.execute(
            text(
                "INSERT INTO tenants(id,slug,display_name) VALUES(:t,'academy-concurrency','Academy Concurrency') ON CONFLICT(id) DO NOTHING"
            ),
            {"t": TENANT},
        )
        await s.execute(
            text(
                "INSERT INTO academy_content_items(id,tenant_id,content_type,slug,title_i18n,status,created_by) VALUES(:id,:t,'video','concurrency-video','{\"en\":\"Concurrency\"}'::jsonb,'published','ci') ON CONFLICT(id) DO NOTHING"
            ),
            {"id": CONTENT, "t": TENANT},
        )
        await s.execute(
            text(
                "INSERT INTO academy_content_versions(id,tenant_id,content_id,version_label,version_number,locale,duration_ms,status,created_by) VALUES(:id,:t,:c,'1',1,'en',10000,'published','ci') ON CONFLICT(id) DO NOTHING"
            ),
            {"id": VERSION, "t": TENANT, "c": CONTENT},
        )
        await s.execute(
            text(
                "INSERT INTO academy_learning_paths(id,tenant_id,key,title_i18n,status,created_by) VALUES(:id,:t,'concurrency-path','{\"en\":\"Concurrency\"}'::jsonb,'published','ci') ON CONFLICT(id) DO NOTHING"
            ),
            {"id": PATH, "t": TENANT},
        )
        await s.execute(
            text(
                "INSERT INTO academy_learning_path_items(tenant_id,path_id,content_version_id,ordinal,required) VALUES(:t,:p,:v,1,TRUE) ON CONFLICT DO NOTHING"
            ),
            {"t": TENANT, "p": PATH, "v": VERSION},
        )
        await s.execute(
            text(
                "INSERT INTO academy_enrollments(id,tenant_id,path_id,subject,source,status,assigned_by) VALUES(:id,:t,:p,'employee','manual','in_progress','ci') ON CONFLICT(id) DO NOTHING"
            ),
            {"id": ENROLLMENT, "t": TENANT, "p": PATH},
        )
        await s.execute(
            text(
                "INSERT INTO academy_progress(id,tenant_id,enrollment_id,content_version_id,subject,status,revision) VALUES(:id,:t,:e,:v,'employee','in_progress',1) ON CONFLICT(id) DO UPDATE SET revision=1"
            ),
            {"id": PROGRESS, "t": TENANT, "e": ENROLLMENT, "v": VERSION},
        )

    ready = asyncio.Event()
    started = 0
    lock = asyncio.Lock()

    async def writer(position: int) -> int | None:
        nonlocal started
        async with Session() as s, s.begin():
            await tenant_context(s)
            async with lock:
                started += 1
                if started == 2:
                    ready.set()
            await ready.wait()
            return await s.scalar(
                text(
                    "UPDATE academy_progress SET last_position_ms=:p, max_position_ms=GREATEST(max_position_ms,:p), revision=revision+1 WHERE tenant_id=:t AND id=:id AND revision=1 RETURNING revision"
                ),
                {"p": position, "t": TENANT, "id": PROGRESS},
            )

    results = await asyncio.gather(writer(5000), writer(6000))
    assert sorted(value for value in results if value is not None) == [2]
    assert sum(value is None for value in results) == 1

    async with Session() as s, s.begin():
        await tenant_context(s)
        row = (
            (
                await s.execute(
                    text(
                        "SELECT revision,last_position_ms,max_position_ms FROM academy_progress WHERE id=:id"
                    ),
                    {"id": PROGRESS},
                )
            )
            .mappings()
            .one()
        )
        assert row["revision"] == 2
        assert row["last_position_ms"] in {5000, 6000}
        assert row["max_position_ms"] == row["last_position_ms"]
