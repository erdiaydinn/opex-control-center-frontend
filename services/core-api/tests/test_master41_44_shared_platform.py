from pathlib import Path

import pytest

from app.shared_platform.contracts import validate_authority_boundary

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/0042_shared_platform_authorities.py"


def test_shared_authorities_are_fail_closed_without_audit_scoring() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "audit_field_binding",
        "platform_notification_outbox",
        "operational_search_document",
        "integration_contract_version",
        "FORCE ROW LEVEL SECURITY",
        "approved integration contract is immutable",
        "independent integration contract approval required",
    ):
        assert token in migration
    assert "capa_score" not in migration.lower()
    assert "audit_score" not in migration.lower()


def test_payload_cannot_author_tenant() -> None:
    assert validate_authority_boundary(tenant_from_session="tenant-a") == "tenant-a"
    with pytest.raises(ValueError, match="payload tenant authority"):
        validate_authority_boundary(
            tenant_from_session="tenant-a",
            tenant_from_payload="tenant-b",
        )
    with pytest.raises(ValueError, match="server tenant authority"):
        validate_authority_boundary(tenant_from_session="")
