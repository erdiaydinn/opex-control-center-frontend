from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.field_intelligence.repository import (
    FieldRepositoryError,
    _validate_evidence_payload,
)
from app.modules.field_intelligence.schemas import (
    EvidenceReview,
    EvidenceSubmit,
    LocalizedText,
    TargetSelector,
    TemplateCreate,
    TemplateFieldDefinition,
    TemplateSchema,
)

FIELD_TYPES = (
    "text",
    "number",
    "select",
    "barcode",
    "qr",
    "photo",
    "lot",
    "batch",
    "expiry",
    "quantity",
    "measurement",
    "gps",
    "yes_no",
    "multi_row",
)


def _field(field_type: str, *, key: str | None = None, required: bool = False):
    return TemplateFieldDefinition(
        key=key or field_type,
        type=field_type,
        label=LocalizedText(values={"en": field_type}),
        required=required,
        options=("a", "b") if field_type == "select" else (),
        config={"max_rows": 2} if field_type == "multi_row" else {},
    )


def test_template_contract_supports_item_8_input_types() -> None:
    schema = TemplateSchema(fields=tuple(_field(field_type) for field_type in FIELD_TYPES))
    template = TemplateCreate(
        template_id="warehouse-proof",
        version=1,
        name=LocalizedText(values={"tr": "Depo kanıtı", "en": "Warehouse evidence"}),
        schema=schema,
        status="draft",
    )
    assert tuple(field.type for field in template.schema.fields) == FIELD_TYPES


def test_template_rejects_unknown_type_duplicate_key_and_unknown_locale() -> None:
    with pytest.raises(ValidationError, match="unsupported field type"):
        _field("script")

    with pytest.raises(ValidationError, match="unique"):
        TemplateSchema(fields=(_field("text", key="same"), _field("number", key="same")))

    with pytest.raises(ValidationError, match="unsupported locales"):
        LocalizedText(values={"xx": "not allowed"})


def test_select_requires_governed_options() -> None:
    with pytest.raises(ValidationError, match="select fields require options"):
        TemplateFieldDefinition(
            key="condition",
            type="select",
            label=LocalizedText(values={"en": "Condition"}),
        )


def test_browser_payload_cannot_supply_tenant_or_role_authority() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceSubmit(
            client_submission_id=uuid4(),
            payload={"lot": "24F17"},
            tenant_id="browser-tenant",
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceSubmit(
            client_submission_id=uuid4(),
            payload={"lot": "24F17"},
            role="super_admin",
        )


def test_evidence_validation_rejects_unknown_fields_and_raw_photo_transport() -> None:
    schema = TemplateSchema(
        fields=(
            _field("lot", required=True),
            _field("photo", required=True),
        )
    ).model_dump(mode="json")

    with pytest.raises(FieldRepositoryError, match="unknown fields"):
        _validate_evidence_payload(
            schema,
            {"lot": "24F17", "photo": {}, "extra": "browser-owned"},
        )

    with pytest.raises(FieldRepositoryError, match="private evidence reference"):
        _validate_evidence_payload(
            schema,
            {"lot": "24F17", "photo": "data:image/jpeg;base64,AAAA"},
        )

    _validate_evidence_payload(
        schema,
        {
            "lot": "24F17",
            "photo": {
                "evidence_reference": "private-evidence://object/42",
                "fingerprint": "a" * 64,
            },
        },
    )


def test_gps_quantity_select_and_multirow_fail_closed() -> None:
    schema = TemplateSchema(
        fields=(
            _field("gps", required=True),
            _field("quantity", required=True),
            _field("select", required=True),
            _field("multi_row"),
        )
    ).model_dump(mode="json")

    with pytest.raises(FieldRepositoryError, match="GPS coordinates are out of range"):
        _validate_evidence_payload(
            schema,
            {
                "gps": {"latitude": 91.0, "longitude": 29.0, "accuracy_m": 4.0},
                "quantity": 1,
                "select": "a",
            },
        )

    with pytest.raises(FieldRepositoryError, match="cannot be negative"):
        _validate_evidence_payload(
            schema,
            {
                "gps": {"latitude": 41.0, "longitude": 29.0, "accuracy_m": 4.0},
                "quantity": -1,
                "select": "a",
            },
        )

    with pytest.raises(FieldRepositoryError, match="configured option"):
        _validate_evidence_payload(
            schema,
            {
                "gps": {"latitude": 41.0, "longitude": 29.0, "accuracy_m": 4.0},
                "quantity": 1,
                "select": "not-configured",
            },
        )

    with pytest.raises(FieldRepositoryError, match="invalid rows"):
        _validate_evidence_payload(
            schema,
            {
                "gps": {"latitude": 41.0, "longitude": 29.0, "accuracy_m": 4.0},
                "quantity": 1,
                "select": "a",
                "multi_row": [{"value": "1"}, {"value": "2"}, {"value": "3"}],
            },
        )


def test_review_requires_reason_for_rework_or_reject() -> None:
    assert EvidenceReview(decision="accept").reason is None
    with pytest.raises(ValidationError, match="requires a reason"):
        EvidenceReview(decision="rework")
    with pytest.raises(ValidationError, match="requires a reason"):
        EvidenceReview(decision="reject", reason="   ")


def test_target_selector_fails_closed_without_positive_scope() -> None:
    with pytest.raises(ValidationError, match="positive target selector"):
        TargetSelector(exclude_location_ids=("WH-1",))
    with pytest.raises(ValidationError, match="both included and excluded"):
        TargetSelector(include_location_ids=("WH-1",), exclude_location_ids=("WH-1",))
