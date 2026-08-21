from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .kpi_nsfr_invariants import verify_nsfr_row


class KpiResultValidationError(ValueError):
    """Raised when a query result violates the reviewed KPI result contract."""


ResultValidator = Callable[[Sequence[Mapping[str, object]]], None]


@dataclass(frozen=True)
class KpiResultContract:
    contract_id: str
    metric: str
    required_fields: tuple[str, ...]
    validator: ResultValidator
    version: str = "1"

    @property
    def fingerprint(self) -> str:
        payload = {
            "contract_id": self.contract_id,
            "metric": self.metric,
            "required_fields": list(self.required_fields),
            "validator": f"{self.validator.__module__}.{self.validator.__qualname__}",
            "version": self.version,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_nsfr_family(rows: Sequence[Mapping[str, object]]) -> None:
    for index, row in enumerate(rows):
        try:
            verify_nsfr_row(row)
        except ValueError as exc:
            raise KpiResultValidationError(
                f"kpi_result_contract_failed:nsfr_family:row={index}:{exc}"
            ) from exc


NSFR_RESULT_FIELDS = (
    "successful_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)


KPI_RESULT_CONTRACTS: dict[str, KpiResultContract] = {
    metric: KpiResultContract(
        contract_id="ops.nsfr-family.result.v2",
        metric=metric,
        required_fields=NSFR_RESULT_FIELDS,
        validator=_validate_nsfr_family,
        version="2",
    )
    for metric in ("nsfr", "pfr", "refund")
}


def get_result_contract(metric: str) -> KpiResultContract | None:
    return KPI_RESULT_CONTRACTS.get(metric)


def get_result_contract_fingerprint(metric: str) -> str | None:
    contract = get_result_contract(metric)
    return contract.fingerprint if contract else None


def validate_kpi_result(metric: str, rows: Sequence[Mapping[str, object]]) -> None:
    contract = get_result_contract(metric)
    if contract is None:
        return
    for index, row in enumerate(rows):
        missing = [field for field in contract.required_fields if field not in row]
        if missing:
            raise KpiResultValidationError(
                "kpi_result_contract_missing_fields:"
                f"metric={metric}:row={index}:fields={','.join(missing)}"
            )
    contract.validator(rows)


class ResultValidatingAdapter:
    """Adapter wrapper that validates BigQuery rows before the executor can audit success."""

    def __init__(self, adapter: Any, *, metric: str):
        self.adapter = adapter
        self.metric = metric

    def dry_run(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int) -> int:
        return self.adapter.dry_run(sql, parameters, timeout_ms=timeout_ms)

    def execute(
        self,
        sql: str,
        parameters: dict[str, Any],
        *,
        timeout_ms: int,
        maximum_bytes_billed: int,
    ) -> list[dict[str, Any]]:
        rows = self.adapter.execute(
            sql,
            parameters,
            timeout_ms=timeout_ms,
            maximum_bytes_billed=maximum_bytes_billed,
        )
        validate_kpi_result(self.metric, rows)
        return rows
