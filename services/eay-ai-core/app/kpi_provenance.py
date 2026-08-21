from __future__ import annotations

import hashlib
import json
from typing import Mapping


_FINGERPRINT_FIELDS = (
    "semantic_fingerprint",
    "schema_fingerprint",
    "schema_evidence_fingerprint",
    "unit_contract_fingerprint",
    "aggregation_contract_fingerprint",
    "policy_contract_fingerprint",
    "formula_contract_fingerprint",
)


def _validate_sha256(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"kpi_provenance_invalid_fingerprint:{field}")
    return text


def activation_provenance_fingerprint(
    *,
    metric: str,
    semantic_fingerprint: object,
    schema_fingerprint: object,
    schema_evidence_fingerprint: object = None,
    unit_contract_fingerprint: object = None,
    aggregation_contract_fingerprint: object = None,
    policy_contract_fingerprint: object = None,
    formula_contract_fingerprint: object = None,
) -> str:
    """Bind all reviewed KPI activation lineage into one deterministic digest.

    Optional runtime fingerprints remain explicit ``null`` values in the canonical payload;
    this prevents KPIs with different runtime-policy shapes from being treated as equivalent
    when unit, aggregation, SLA/policy or formula contracts are absent.
    """

    if not metric.strip():
        raise ValueError("kpi_provenance_metric_required")
    payload = {
        "metric": metric,
        "semantic_fingerprint": _validate_sha256(semantic_fingerprint, "semantic"),
        "schema_fingerprint": _validate_sha256(schema_fingerprint, "schema"),
        "schema_evidence_fingerprint": _validate_sha256(
            schema_evidence_fingerprint, "schema_evidence", optional=True
        ),
        "unit_contract_fingerprint": _validate_sha256(
            unit_contract_fingerprint, "unit_contract", optional=True
        ),
        "aggregation_contract_fingerprint": _validate_sha256(
            aggregation_contract_fingerprint, "aggregation_contract", optional=True
        ),
        "policy_contract_fingerprint": _validate_sha256(
            policy_contract_fingerprint, "policy_contract", optional=True
        ),
        "formula_contract_fingerprint": _validate_sha256(
            formula_contract_fingerprint, "formula_contract", optional=True
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def provenance_from_activation(
    *,
    metric: str,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
    runtime_activation: Mapping[str, object] | None,
) -> str:
    return activation_provenance_fingerprint(
        metric=metric,
        semantic_fingerprint=semantic_verification.get("fingerprint"),
        schema_fingerprint=schema_verification.get("observed_fingerprint"),
        schema_evidence_fingerprint=schema_verification.get("evidence_fingerprint"),
        unit_contract_fingerprint=(
            runtime_activation.get("unit_contract_fingerprint") if runtime_activation else None
        ),
        aggregation_contract_fingerprint=(
            runtime_activation.get("aggregation_contract_fingerprint") if runtime_activation else None
        ),
        policy_contract_fingerprint=(
            runtime_activation.get("sla_contract_fingerprint") if runtime_activation else None
        ),
        formula_contract_fingerprint=(
            runtime_activation.get("quantity_contract_fingerprint") if runtime_activation else None
        ),
    )
