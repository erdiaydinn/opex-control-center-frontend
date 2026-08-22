from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.planogram.fixture_catalog import (
    approved_fixture_to_scanned_binding,
)
from app.modules.planogram.fixture_catalog_schemas import PlanogramTrustedFixtureBinding
from app.modules.planogram.repository_fixture_catalog import (
    get_approved_fixture_catalog_versions,
)


async def resolve_trusted_fixture_bindings(
    session: AsyncSession,
    principal: Principal,
    bindings: list[PlanogramTrustedFixtureBinding],
) -> list[dict[str, object]]:
    """Resolve topology-only client bindings into server-approved physical truth."""

    versions = await get_approved_fixture_catalog_versions(
        session,
        principal,
        [binding.approved_catalog_version_id for binding in bindings],
    )
    resolved: list[dict[str, object]] = []
    for binding in bindings:
        approved = versions[binding.approved_catalog_version_id]
        resolved.append(
            approved_fixture_to_scanned_binding(
                approved,
                scan_fixture_element_id=binding.scan_fixture_element_id,
                aisle_id=binding.aisle_id,
                side=binding.side,
                position=binding.position,
                expected_record_sha256=binding.expected_record_sha256,
            )
        )
    return resolved
