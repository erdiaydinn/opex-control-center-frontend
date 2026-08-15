from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.data_collection.schemas import (
    CollectionField,
    CollectionSubmission,
    CollectionTemplate,
    FieldType,
    RecordKind,
    SubmissionContext,
)
from app.modules.data_collection.service import CollectionValidationError, validate_submission


@pytest.fixture
def template() -> CollectionTemplate:
    return CollectionTemplate(
        template_id="warehouse.physical_truth",
        name="Warehouse physical truth",
        version=1,
        record_kind=RecordKind.GENERIC,
        fields=(
            CollectionField(key="barcode", label="Barcode", field_type=FieldType.BARCODE, required=True),
            CollectionField(key="lot", label="Lot", field_type=FieldType.LOT),
            CollectionField(
                key="quantity",
                label="Quantity",
                field_type=FieldType.QUANTITY,
                required=True,
                min_value=0,
            ),
            CollectionField(
                key="asset_type",
                label="Asset type",
                field_type=FieldType.SELECT,
                required=True,
                options=("product", "pallet", "cabinet", "fixture"),
            ),
        ),
    )


def _submission(values: dict) -> CollectionSubmission:
    return CollectionSubmission(
        template_id="warehouse.physical_truth",
        template_version=1,
        external_record_id="scan-001",
        context=SubmissionContext(
            tenant_id="tenant-a",
            location_id="warehouse-1",
            actor_id="employee-7",
            source="scanner",
            captured_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
            device_id="managed-device-3",
        ),
        values=values,
    )


def test_validates_product_lot_quantity_collection(template: CollectionTemplate) -> None:
    result = validate_submission(
        template,
        _submission(
            {
                "barcode": "869000000001",
                "lot": "LOT-2026-08",
                "quantity": "24",
                "asset_type": "product",
            }
        ),
    )
    assert result.normalized_values["quantity"] == Decimal("24")
    assert result.context.location_id == "warehouse-1"


def test_supports_non_product_physical_assets(template: CollectionTemplate) -> None:
    result = validate_submission(
        template,
        _submission({"barcode": "PALLET-9", "quantity": 3, "asset_type": "pallet"}),
    )
    assert result.normalized_values["asset_type"] == "pallet"


def test_unknown_field_fails_closed(template: CollectionTemplate) -> None:
    with pytest.raises(CollectionValidationError, match="unknown fields"):
        validate_submission(
            template,
            _submission({"barcode": "X", "quantity": 1, "asset_type": "cabinet", "tenant_id": "smuggled"}),
        )


def test_negative_quantity_fails_closed(template: CollectionTemplate) -> None:
    with pytest.raises(CollectionValidationError, match="below minimum"):
        validate_submission(
            template,
            _submission({"barcode": "X", "quantity": -1, "asset_type": "fixture"}),
        )


def test_template_version_substitution_fails_closed(template: CollectionTemplate) -> None:
    bad = _submission({"barcode": "X", "quantity": 1, "asset_type": "product"}).model_copy(
        update={"template_version": 2}
    )
    with pytest.raises(CollectionValidationError, match="template identity/version mismatch"):
        validate_submission(template, bad)
