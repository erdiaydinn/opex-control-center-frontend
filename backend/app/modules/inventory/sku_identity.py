"""Safe server-frozen SKU identity projection for blind count events."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .production import canonical_payload_hash


def frozen_sku_identity(
    document_id: UUID,
    barcode: str,
    expected_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Prove one scanned identity without exposing stock or the SKU universe."""

    normalized_barcode = str(barcode).strip()
    sku = str(expected_row["sku"]).strip() if expected_row else None
    status = "KNOWN" if sku else "UNEXPECTED"
    snapshot_input = {
        "barcode": normalized_barcode,
        "document_id": str(document_id),
        "sku": sku,
        "status": status,
    }
    return {
        **snapshot_input,
        "snapshot_hash": canonical_payload_hash(snapshot_input),
    }
