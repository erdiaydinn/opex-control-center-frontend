from __future__ import annotations

from collections.abc import Iterable, Mapping

from .kpi_schema_evidence import KpiSchemaEvidence


def import_information_schema_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    expected_table: str,
    captured_at: str,
    source: str,
    reviewer: str | None,
    reviewed: bool,
) -> KpiSchemaEvidence:
    """Build immutable schema evidence from a BigQuery INFORMATION_SCHEMA export.

    Accepted input is intentionally narrow: each row must expose `table_name`,
    `column_name`, and `data_type`. The importer does not infer KPI semantics and does
    not accept aliases for those fields, so spreadsheet/manual exports cannot silently
    change meaning during ingestion.
    """

    observed: dict[str, str] = {}
    row_count = 0
    for index, row in enumerate(rows):
        row_count += 1
        missing = [field for field in ("table_name", "column_name", "data_type") if field not in row]
        if missing:
            raise ValueError(
                "kpi_schema_import_missing_fields:"
                f"row={index}:fields={','.join(missing)}"
            )
        table_name = str(row["table_name"] or "").strip()
        column_name = str(row["column_name"] or "").strip().lower()
        data_type = str(row["data_type"] or "").strip().upper()
        if table_name != expected_table:
            raise ValueError(
                f"kpi_schema_import_unexpected_table:row={index}:table={table_name}"
            )
        if not column_name:
            raise ValueError(f"kpi_schema_import_blank_column:row={index}")
        if not data_type:
            raise ValueError(f"kpi_schema_import_blank_type:row={index}:column={column_name}")
        prior = observed.get(column_name)
        if prior is not None and prior != data_type:
            raise ValueError(
                "kpi_schema_import_conflicting_duplicate:"
                f"column={column_name}:first={prior}:second={data_type}"
            )
        observed[column_name] = data_type

    if row_count == 0:
        raise ValueError("kpi_schema_import_empty_export")

    return KpiSchemaEvidence(
        table_id=expected_table,
        observed_columns=observed,
        captured_at=captured_at,
        source=source,
        reviewer=reviewer,
        reviewed=reviewed,
    )
