from pathlib import Path
import pytest
from app.shared_platform.contracts import validate_authority_boundary


def test_shared_authorities_are_fail_closed_and_audit_scoring_is_not_hardcoded():
    migration=(Path(__file__).resolve().parents[1]/'alembic/versions/0041_shared_platform_authorities.py').read_text()
    for token in ('audit_field_binding','platform_notification_outbox','operational_search_document','integration_contract_version','FORCE ROW LEVEL SECURITY','approved integration contract is immutable'):
        assert token in migration
    assert 'capa_score' not in migration.lower() and 'audit_score' not in migration.lower()


def test_payload_cannot_author_tenant():
    assert validate_authority_boundary(tenant_from_session='tenant-a')=='tenant-a'
    with pytest.raises(ValueError): validate_authority_boundary(tenant_from_session='tenant-a',tenant_from_payload='tenant-b')
