from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from contextlib import suppress
from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")


def money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def amount_mismatch(
    expected: object,
    observed: object,
    *,
    tolerance_bps: int = 50,
    absolute: object = "1.00",
) -> bool:
    expected_d = money(expected)
    observed_d = money(observed)
    allowed = max(
        money(absolute),
        (
            abs(expected_d)
            * Decimal(tolerance_bps)
            / Decimal(10000)
        ).quantize(MONEY),
    )
    return abs(expected_d - observed_d) > allowed


def normalize_import_row(row: Mapping[str, object]) -> dict[str, str]:
    numeric = {
        "amount",
        "budget_amount",
        "forecast_base_amount",
        "requested_amount",
        "po_amount",
        "invoice_amount",
        "rate",
    }
    identifiers = {
        "external_id",
        "external_ref",
        "invoice_number",
        "supplier_id",
        "currency",
        "cost_center_code",
    }
    out: dict[str, str] = {}
    for raw_key, raw_value in sorted(
        row.items(),
        key=lambda item: str(item[0]).lower(),
    ):
        key = str(raw_key).strip().lower()
        if not key:
            continue
        value = "" if raw_value is None else str(raw_value).strip()
        if not value:
            continue
        if key in numeric:
            with suppress(Exception):
                value = str(money(value))
        elif key in identifiers:
            value = value.upper()
        out[key] = value
    return out


def row_fingerprint(
    row: Mapping[str, object],
    *,
    namespace: str = "",
) -> str:
    normalized = normalize_import_row(row)
    payload = json.dumps(
        {"namespace": namespace, "row": normalized},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def batch_hash(
    rows: Iterable[Mapping[str, object]],
    *,
    namespace: str = "",
) -> str:
    payload = json.dumps(
        [row_fingerprint(row, namespace=namespace) for row in rows],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text
