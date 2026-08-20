import pytest

from app.modules.planogram.retail_intelligence_guard import (
    assert_retail_payload_safe,
    retail_payload_blockers,
)


def test_blocks_nested_customer_and_order_identity():
    payload = {
        "products": [{"sku": "SKU-1", "customer_id": "hidden"}],
        "metadata": {"order_id": "order-1"},
    }
    blockers = retail_payload_blockers(payload)
    assert any("customer_id" in blocker for blocker in blockers)
    assert any("order_id" in blocker for blocker in blockers)
    with pytest.raises(ValueError):
        assert_retail_payload_safe(payload)


def test_allows_operational_product_and_source_fields():
    assert_retail_payload_safe(
        {
            "sku": "SKU-1",
            "store_code": "STORE-1",
            "source_ref": "warehouse://sku/1",
            "gross_margin_value": 12.5,
        }
    )
