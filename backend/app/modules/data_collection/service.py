from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.data_collection.schemas import (
    CollectionField,
    CollectionSubmission,
    CollectionTemplate,
    FieldType,
    ValidatedSubmission,
)


class CollectionValidationError(ValueError):
    pass


def _number(value: Any, *, integer: bool) -> int | Decimal:
    if isinstance(value, bool):
        raise CollectionValidationError("boolean is not a numeric value")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CollectionValidationError("invalid numeric value") from exc
    if integer:
        if parsed != parsed.to_integral_value():
            raise CollectionValidationError("integer field requires a whole number")
        return int(parsed)
    return parsed


def _validate_scalar(field: CollectionField, value: Any) -> Any:
    if field.field_type in {FieldType.TEXT, FieldType.BARCODE, FieldType.LOT, FieldType.PHOTO}:
        if not isinstance(value, str) or not value.strip():
            raise CollectionValidationError(f"{field.key} requires non-empty text")
        return value.strip()
    if field.field_type is FieldType.INTEGER:
        result = _number(value, integer=True)
    elif field.field_type in {FieldType.DECIMAL, FieldType.QUANTITY}:
        result = _number(value, integer=False)
    elif field.field_type is FieldType.BOOLEAN:
        if not isinstance(value, bool):
            raise CollectionValidationError(f"{field.key} requires boolean")
        return value
    elif field.field_type is FieldType.SELECT:
        if value not in field.options:
            raise CollectionValidationError(f"{field.key} contains an unknown option")
        return value
    elif field.field_type is FieldType.DATE:
        try:
            return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value))
        except ValueError as exc:
            raise CollectionValidationError(f"{field.key} requires ISO date") from exc
    elif field.field_type is FieldType.DATETIME:
        try:
            return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise CollectionValidationError(f"{field.key} requires ISO datetime") from exc
    else:
        raise CollectionValidationError(f"unsupported field type: {field.field_type}")

    numeric = Decimal(str(result))
    if field.min_value is not None and numeric < Decimal(str(field.min_value)):
        raise CollectionValidationError(f"{field.key} is below minimum")
    if field.max_value is not None and numeric > Decimal(str(field.max_value)):
        raise CollectionValidationError(f"{field.key} exceeds maximum")
    return result


def validate_submission(template: CollectionTemplate, submission: CollectionSubmission) -> ValidatedSubmission:
    if submission.template_id != template.template_id or submission.template_version != template.version:
        raise CollectionValidationError("template identity/version mismatch")

    configured = {field.key: field for field in template.fields}
    unknown = sorted(set(submission.values) - set(configured))
    if unknown:
        raise CollectionValidationError(f"unknown fields: {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    for field in template.fields:
        present = field.key in submission.values and submission.values[field.key] is not None
        if field.required and not present:
            raise CollectionValidationError(f"missing required field: {field.key}")
        if present:
            normalized[field.key] = _validate_scalar(field, submission.values[field.key])

    return ValidatedSubmission(
        template_id=template.template_id,
        template_version=template.version,
        record_kind=template.record_kind,
        context=submission.context,
        normalized_values=normalized,
        external_record_id=submission.external_record_id,
    )
