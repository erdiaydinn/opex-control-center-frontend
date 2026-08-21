from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.permission_catalog import is_known_permission
from app.field_promotion_routes import ConsumerReceipt, PromotionCreate
from app.main import app
from app.modules.field_intelligence.promotion import FieldPromotionError, get_adapter


def test_item10_routes_are_registered_on_canonical_core_api() -> None:
    paths = set(app.openapi()["paths"])
    assert "/v1/field/promotions" in paths
    assert "/v1/field/promotions/{promotion_id}/decision" in paths
    assert "/v1/field/promotions/{promotion_id}/consumer-receipt" in paths


def test_browser_cannot_supply_tenant_or_candidate_truth_in_promotion_request() -> None:
    with pytest.raises(ValidationError):
        PromotionCreate.model_validate(
            {
                "evidence_id": "00000000-0000-0000-0000-000000000001",
                "adapter_key": "inventory.count_observation.v1",
                "tenant_id": "attacker-tenant",
            }
        )

    with pytest.raises(ValidationError):
        PromotionCreate.model_validate(
            {
                "evidence_id": "00000000-0000-0000-0000-000000000001",
                "adapter_key": "inventory.count_observation.v1",
                "candidate_payload": {"quantity": 999999},
            }
        )


def test_all_consumer_permissions_are_core_catalog_authority() -> None:
    for permission in (
        "action:field_intelligence:proposePromotion",
        "action:field_intelligence:approvePromotion",
        "action:field_intelligence:viewPromotions",
        "action:inventory:acceptFieldEvidence",
        "action:planogram:acceptFieldEvidence",
        "action:budget:acceptFieldEvidence",
    ):
        assert is_known_permission(permission), permission


def test_planogram_adapter_builds_candidate_not_physical_truth() -> None:
    adapter = get_adapter("planogram.fixture_measurement.v1")
    candidate = adapter.build_candidate(
        {
            "fixture_id": "fixture-a",
            "width_mm": 1200,
            "height_mm": 2200,
            "depth_mm": 600,
            "aisle_width_mm": 1300,
        },
        "store-a",
    )
    assert adapter.consumer_module == "planogram"
    assert candidate["physical_master_write_permitted"] is False
    assert candidate["requires_planogram_validation_and_approval"] is True
    assert candidate["location_id"] == "store-a"


def test_inventory_adapter_requires_identity_and_never_writes_inventory_truth() -> None:
    adapter = get_adapter("inventory.count_observation.v1")
    with pytest.raises(FieldPromotionError, match="sku or pallet_id"):
        adapter.build_candidate({"quantity": 1, "uom": "EA"}, "store-a")

    candidate = adapter.build_candidate(
        {"sku": "123456789", "quantity": 4, "uom": "EA"},
        "store-a",
    )
    assert candidate["inventory_truth_write_permitted"] is False
    assert candidate["requires_inventory_reconciliation_and_approval"] is True


def test_budget_adapter_is_supporting_evidence_only() -> None:
    adapter = get_adapter("budget.supporting_evidence.v1")
    candidate = adapter.build_candidate(
        {
            "cost_center": "CC-TR-001",
            "amount_minor_units": 125000,
            "currency": "TRY",
            "expense_date": "2026-08-17",
        },
        "store-a",
    )
    assert candidate["financial_posting_permitted"] is False
    assert candidate["requires_finance_reconciliation_and_approval"] is True


def test_consumer_receipt_is_strict_and_does_not_accept_truth_flags() -> None:
    with pytest.raises(ValidationError):
        ConsumerReceipt.model_validate(
            {
                "consumer_module": "inventory",
                "decision": "accept",
                "destination_candidate_ref": "inventory-draft-123",
                "truth_mutation_permitted": True,
            }
        )


def test_promotion_runtime_cannot_directly_mutate_consumer_authority_tables() -> None:
    import app.modules.field_intelligence.promotion as promotion

    source = inspect.getsource(promotion).lower()
    forbidden_sql = (
        "insert into inventory_",
        "update inventory_",
        "delete from inventory_",
        "insert into planogram_",
        "update planogram_",
        "delete from planogram_",
        "insert into budget_",
        "update budget_",
        "delete from budget_",
        "insert into financial_",
        "update financial_",
    )
    assert not any(token in source for token in forbidden_sql)
    assert "truth_mutation_permitted" in source
    assert "consumer_truth_requires_separate_module_workflow" in source


def test_migration_keeps_promotion_evidence_append_only_and_rls_bound() -> None:
    migration = Path(
        "services/core-api/alembic/versions/0023_field_governed_promotion.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str = "0022_field_evidence_integrity"' in migration
    for table in (
        "field_promotion_requests",
        "field_promotion_decisions",
        "field_promotion_consumer_receipts",
    ):
        assert table in migration
        assert (
            f'_tenant_policy("{table}")' not in migration
            or "_tenant_policy(table_name)" in migration
        )
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "prevent_field_evidence_mutation" in migration
    assert "GRANT SELECT, INSERT" in migration
