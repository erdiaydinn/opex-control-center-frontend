from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.planogram.fixture_catalog import (
    FixtureCatalogStateError,
    approved_fixture_to_scanned_binding,
    canonical_fixture_record,
    fixture_record_fingerprint,
)
from app.modules.planogram.fixture_catalog_schemas import PlanogramTrustedFixtureBinding


def _record(storage_type: str = "CHILLED") -> dict[str, object]:
    return {
        "fixture_code": "CHILLER-A",
        "fixture_name": "Chiller A",
        "fixture_type": "CHILLER",
        "storage_type": storage_type,
        "shelf_count": 4,
        "fixture_width_cm": 120.0,
        "fixture_height_cm": 210.0,
        "fixture_depth_cm": 75.0,
        "shelf_width_cm": 115.0,
        "shelf_height_cm": 45.0,
        "shelf_depth_cm": 70.0,
        "shelf_max_weight_kg": 55.0,
        "shelf_zone_types": ["bottom", "lower", "eye", "upper"],
        "measured_source": "surveyed_fixture_catalog",
        "source_ref": "fixture-survey-2026-08-20",
    }


def test_fixture_record_fingerprint_is_deterministic() -> None:
    first = canonical_fixture_record(_record())
    second = canonical_fixture_record(dict(reversed(list(_record().items()))))
    assert fixture_record_fingerprint(first) == fixture_record_fingerprint(second)


def test_trusted_binding_schema_forbids_browser_physical_authority() -> None:
    with pytest.raises(ValidationError):
        PlanogramTrustedFixtureBinding.model_validate(
            {
                "scan_fixture_element_id": "scan-1",
                "approved_catalog_version_id": str(uuid4()),
                "aisle_id": "A1",
                "side": "L",
                "position": 1,
                "storage_type": "AMBIENT",
                "attested": True,
                "fixture_width_cm": 999,
            }
        )


def test_approved_fixture_resolves_server_truth_and_stale_sha_fails() -> None:
    version_id = uuid4()
    record = canonical_fixture_record(_record())
    sha = fixture_record_fingerprint(record)
    approved = {
        "id": version_id,
        "status": "approved",
        "version_number": 3,
        "record": record,
        "record_sha256": sha,
    }
    binding = approved_fixture_to_scanned_binding(
        approved,
        scan_fixture_element_id="scan-chiller-1",
        aisle_id="COLD-1",
        side="L",
        position=1,
        expected_record_sha256=sha,
    )
    assert binding["storage_type"] == "CHILLED"
    assert binding["attested"] is True
    assert str(version_id) in binding["source_ref"]
    assert binding["fixture_width_cm"] == 120.0

    with pytest.raises(FixtureCatalogStateError) as exc:
        approved_fixture_to_scanned_binding(
            approved,
            scan_fixture_element_id="scan-chiller-1",
            aisle_id="COLD-1",
            side="L",
            position=1,
            expected_record_sha256="0" * 64,
        )
    assert exc.value.code == "fixture_catalog_version_stale_or_changed"


def test_fixture_catalog_migration_is_tenant_safe_immutable_and_maker_checker_ready() -> None:
    migration = Path("alembic/versions/0046_planogram_fixture_catalog_authority.py").read_text()
    assert 'down_revision: str = "0045_academy_content_locale_expansion"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "current_setting('app.tenant_id', true)" in migration
    assert "approved -> superseded" in migration
    assert "uq_planogram_fixture_catalog_approved" in migration


def test_repository_enforces_tenant_scope_and_maker_checker() -> None:
    repository = Path("app/modules/planogram/repository_fixture_catalog.py").read_text()
    assert repository.count("tenant_id=:tenant_id") >= 8
    assert 'target["submitted_by"] == principal.subject' in repository
    assert 'FixtureCatalogStateError("maker_checker_required")' in repository
    assert "status='approved'" in repository


def test_trusted_scan_router_never_grants_release_authority() -> None:
    router = Path("app/modules/planogram/store_scan_trusted_router.py").read_text()
    assert '"fixture_catalog_authoritative": True' in router
    assert router.count('"production_release_allowed": False') == 2
    assert router.count('"store_dna_approval_allowed": False') == 2
    assert "server_approved_fixture_catalog_scan_binding_v1" in router
    assert "server_approved_fixture_catalog_scanned_v2_optimizer_v1" in router
