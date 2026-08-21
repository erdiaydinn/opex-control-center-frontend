from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .kpi_putaway_sla import PutawaySlaContract, resolve_putaway_sla_contract


@dataclass(frozen=True)
class PutawayQuantityContract:
    metric: str = "putaway"
    initial_field: str = "putaway_qty_initial"
    on_shelf_field: str = "putaway_qty_on_shelf"
    output_field: str = "issue_qty"

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "initial_field": self.initial_field,
            "on_shelf_field": self.on_shelf_field,
            "output_field": self.output_field,
            "formula": "putaway_qty_initial-putaway_qty_on_shelf",
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def issue_quantity(self, *, initial: object, on_shelf: object) -> Decimal:
        initial_value = _non_negative_decimal(initial, self.initial_field)
        on_shelf_value = _non_negative_decimal(on_shelf, self.on_shelf_field)
        if on_shelf_value > initial_value:
            raise ValueError("putaway_quantity_on_shelf_exceeds_initial")
        return initial_value - on_shelf_value


@dataclass(frozen=True)
class PutawayActivationBundle:
    metric: str
    semantic_fingerprint: str
    schema_fingerprint: str
    schema_evidence_fingerprint: str
    sla_contract_fingerprint: str
    quantity_contract_fingerprint: str

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "semantic_fingerprint": self.semantic_fingerprint,
            "schema_fingerprint": self.schema_fingerprint,
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "sla_contract_fingerprint": self.sla_contract_fingerprint,
            "quantity_contract_fingerprint": self.quantity_contract_fingerprint,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _non_negative_decimal(value: object, field: str) -> Decimal:
    if value is None:
        raise ValueError(f"putaway_quantity_missing:{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"putaway_quantity_non_numeric:{field}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"putaway_quantity_invalid:{field}")
    return number


def _sha256(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"putaway_activation_invalid_fingerprint:{field}")
    return text


def verify_putaway_activation(
    *,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
    sla_contracts: Sequence[PutawaySlaContract],
    as_of,
    quantity_contract: PutawayQuantityContract | None = None,
) -> PutawayActivationBundle:
    """Bind putaway semantics, reviewed live schema, SLA version and quantity formula.

    Putaway activation is intentionally stricter than generic KPI activation because the
    result depends on both a temporal SLA policy and a source-field subtraction formula.
    A human-reviewed schema-evidence fingerprint is mandatory; live-schema verification
    without evidence lineage is insufficient for production activation.
    """

    if semantic_verification.get("metric") != "putaway" or semantic_verification.get("reviewed") is not True:
        raise ValueError("putaway_activation_semantic_verification_required")
    if schema_verification.get("verified") is not True:
        raise ValueError("putaway_activation_schema_verification_required")

    semantic_fp = _sha256(semantic_verification.get("fingerprint"), "semantic")
    schema_fp = _sha256(schema_verification.get("observed_fingerprint"), "schema")
    evidence_fp = _sha256(schema_verification.get("evidence_fingerprint"), "schema_evidence")

    sla = resolve_putaway_sla_contract(sla_contracts, as_of=as_of)
    if sla.schema_evidence_fingerprint != evidence_fp:
        raise ValueError("putaway_activation_sla_schema_evidence_mismatch")

    quantity = quantity_contract or PutawayQuantityContract()
    if quantity.metric != "putaway":
        raise ValueError("putaway_activation_quantity_metric_mismatch")

    return PutawayActivationBundle(
        metric="putaway",
        semantic_fingerprint=semantic_fp,
        schema_fingerprint=schema_fp,
        schema_evidence_fingerprint=evidence_fp,
        sla_contract_fingerprint=sla.fingerprint,
        quantity_contract_fingerprint=quantity.fingerprint,
    )
