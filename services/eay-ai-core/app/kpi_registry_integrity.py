from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class KpiRegistryBinding:
    metric: str
    query_id: str
    source_table: str
    schema_contract_id: str
    semantic_contract_id: str
    schema_contract_fingerprint: str
    semantic_contract_fingerprint: str
    query_template_fingerprint: str
    promotion_decision_fingerprint: str | None
    legacy_bootstrap: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "query_id": self.query_id,
            "source_table": self.source_table,
            "schema_contract_id": self.schema_contract_id,
            "semantic_contract_id": self.semantic_contract_id,
            "schema_contract_fingerprint": self.schema_contract_fingerprint,
            "semantic_contract_fingerprint": self.semantic_contract_fingerprint,
            "query_template_fingerprint": self.query_template_fingerprint,
            "promotion_decision_fingerprint": self.promotion_decision_fingerprint,
            "legacy_bootstrap": self.legacy_bootstrap,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"kpi_registry_integrity_invalid_fingerprint:{field}")
    return text


def verify_registry_binding(definition: object) -> KpiRegistryBinding:
    """Fail closed when executable KPI code drifts from reviewed registry lineage.

    The binding covers the query template plus the exact schema and semantic contracts.
    Changing SQL, parameters, schema columns/types or business semantics invalidates the
    previously pinned binding. New KPIs additionally require a human promotion-decision
    fingerprint. Orders remains the sole explicit legacy bootstrap exception.
    """

    metric = str(getattr(definition, "metric", "") or "")
    query_id = str(getattr(definition, "query_id", "") or "")
    source_table = str(getattr(definition, "source_table", "") or "")
    schema_contract_id = str(getattr(definition, "schema_contract_id", "") or "")
    semantic_contract_id = str(getattr(definition, "semantic_contract_id", "") or "")
    expected_template_fp = _sha(getattr(definition, "query_template_fingerprint", None), "query_template")
    expected_schema_fp = _sha(getattr(definition, "schema_contract_fingerprint", None), "schema_contract")
    expected_semantic_fp = _sha(getattr(definition, "semantic_contract_fingerprint", None), "semantic_contract")
    expected_binding_fp = _sha(getattr(definition, "registry_binding_fingerprint", None), "registry_binding")
    promotion_fp_raw = getattr(definition, "registry_promotion_fingerprint", None)
    legacy_bootstrap = bool(getattr(definition, "legacy_bootstrap", False))

    if not all((metric, query_id, source_table, schema_contract_id, semantic_contract_id)):
        raise ValueError(f"kpi_registry_integrity_definition_incomplete:{metric}")
    if legacy_bootstrap and metric != "orders":
        raise ValueError("kpi_registry_integrity_legacy_bootstrap_forbidden")
    if not legacy_bootstrap:
        promotion_fp = _sha(promotion_fp_raw, "registry_promotion")
    else:
        if promotion_fp_raw is not None:
            raise ValueError("kpi_registry_integrity_legacy_promotion_must_be_empty")
        promotion_fp = None

    from .query_templates import TEMPLATES
    from .schema_contracts import get_schema_contract
    from .kpi_semantics import get_semantic_contract

    template = TEMPLATES.get(query_id)
    if template is None:
        raise ValueError(f"kpi_registry_integrity_query_template_missing:{metric}")
    if template.query_id != query_id:
        raise ValueError(f"kpi_registry_integrity_query_id_mismatch:{metric}")
    if template.fingerprint != expected_template_fp:
        raise ValueError(f"kpi_registry_integrity_query_template_drift:{metric}")

    schema_contract = get_schema_contract(schema_contract_id)
    if schema_contract.table_id != source_table:
        raise ValueError(f"kpi_registry_integrity_schema_table_drift:{metric}")
    if schema_contract.expected_fingerprint != expected_schema_fp:
        raise ValueError(f"kpi_registry_integrity_schema_contract_drift:{metric}")

    semantic_contract = get_semantic_contract(semantic_contract_id)
    if semantic_contract.metric != metric:
        raise ValueError(f"kpi_registry_integrity_semantic_metric_drift:{metric}")
    if semantic_contract.fingerprint != expected_semantic_fp:
        raise ValueError(f"kpi_registry_integrity_semantic_contract_drift:{metric}")

    binding = KpiRegistryBinding(
        metric=metric,
        query_id=query_id,
        source_table=source_table,
        schema_contract_id=schema_contract_id,
        semantic_contract_id=semantic_contract_id,
        schema_contract_fingerprint=expected_schema_fp,
        semantic_contract_fingerprint=expected_semantic_fp,
        query_template_fingerprint=expected_template_fp,
        promotion_decision_fingerprint=promotion_fp,
        legacy_bootstrap=legacy_bootstrap,
    )
    if binding.fingerprint != expected_binding_fp:
        raise ValueError(f"kpi_registry_integrity_binding_drift:{metric}")
    return binding
