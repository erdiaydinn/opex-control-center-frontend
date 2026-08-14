from decimal import Decimal

from app.modules.budget.domain import (
    amount_mismatch,
    batch_hash,
    normalize_import_row,
    row_fingerprint,
    safe_csv_cell,
)


def test_money_mismatch_is_tolerance_bound() -> None:
    assert amount_mismatch("100.00", "100.50", tolerance_bps=100, absolute="0.10") is False
    assert amount_mismatch("100.00", "102.00", tolerance_bps=100, absolute="0.10") is True


def test_import_identity_is_canonical_and_namespaced() -> None:
    first = {"supplier_id": " abc ", "amount": Decimal("1.2"), "empty": ""}
    second = {"amount": "1.20", "supplier_id": "ABC"}
    assert normalize_import_row(first) == {"amount": "1.20", "supplier_id": "ABC"}
    assert row_fingerprint(first, namespace="SAP:invoice") == row_fingerprint(
        second,
        namespace="SAP:invoice",
    )
    assert row_fingerprint(first, namespace="SAP:invoice") != row_fingerprint(
        second,
        namespace="ARIBA:invoice",
    )
    assert batch_hash([first], namespace="SAP:invoice") == batch_hash(
        [second],
        namespace="SAP:invoice",
    )


def test_export_cells_neutralize_spreadsheet_formulas() -> None:
    assert safe_csv_cell("=1+1") == "'=1+1"
    assert safe_csv_cell("@SUM(A:A)") == "'@SUM(A:A)"
    assert safe_csv_cell("normal") == "normal"
