from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from .kpi_putaway_contracts import PutawayActivationBundle


@dataclass(frozen=True)
class PutawayProductionActivationArtifact:
    activation_fingerprint: str
    schema_evidence_fingerprint: str
    source_mapping_fingerprint: str
    sla_contract_fingerprint: str
    quantity_contract_fingerprint: str
    approval_reference: str
    reviewer: str
    approved_for_registry_review: bool = True
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": "putaway",
            "activation_fingerprint": self.activation_fingerprint,
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "source_mapping_fingerprint": self.source_mapping_fingerprint,
            "sla_contract_fingerprint": self.sla_contract_fingerprint,
            "quantity_contract_fingerprint": self.quantity_contract_fingerprint,
            "approval_reference": self.approval_reference,
            "reviewer": self.reviewer,
            "approved_for_registry_review": self.approved_for_registry_review,
            "executable": self.executable,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"putaway_production_activation_invalid_fingerprint:{field}")
    return text


def seal_putaway_production_activation(
    *,
    activation: PutawayActivationBundle,
    source_mapping_verification: Mapping[str, object],
    approval_reference: str,
    reviewer: str,
) -> PutawayProductionActivationArtifact:
    """Seal reviewed putaway source semantics around the existing SLA activation bundle.

    This is a review artifact only. It prevents the generic putaway activation bundle
    from being treated as production proof unless the exact source-role mapping is
    tied to the same schema evidence. Registry/execution enablement remains a separate
    human-reviewed code change.
    """

    if activation.metric != "putaway":
        raise ValueError("putaway_production_activation_metric_mismatch")
    if source_mapping_verification.get("verified") is not True:
        raise ValueError("putaway_production_activation_source_mapping_required")
    if source_mapping_verification.get("metric") != "putaway":
        raise ValueError("putaway_production_activation_source_mapping_metric_mismatch")

    activation_evidence = _sha(
        activation.schema_evidence_fingerprint, "activation_schema_evidence"
    )
    mapping_evidence = _sha(
        source_mapping_verification.get("schema_evidence_fingerprint"),
        "mapping_schema_evidence",
    )
    if activation_evidence != mapping_evidence:
        raise ValueError("putaway_production_activation_schema_evidence_mismatch")

    role_map = source_mapping_verification.get("role_to_column")
    role_types = source_mapping_verification.get("role_types")
    if not isinstance(role_map, Mapping) or not isinstance(role_types, Mapping):
        raise ValueError("putaway_production_activation_source_roles_required")
    required = {
        "date",
        "city",
        "inbound_kind",
        "elapsed_minutes",
        "initial_qty",
        "on_shelf_qty",
    }
    if set(required) - set(role_map) or set(required) - set(role_types):
        raise ValueError("putaway_production_activation_source_roles_incomplete")

    approval = approval_reference.strip()
    reviewer_name = reviewer.strip()
    if not approval:
        raise ValueError("putaway_production_activation_approval_reference_required")
    if not reviewer_name:
        raise ValueError("putaway_production_activation_reviewer_required")

    return PutawayProductionActivationArtifact(
        activation_fingerprint=_sha(activation.fingerprint, "activation"),
        schema_evidence_fingerprint=activation_evidence,
        source_mapping_fingerprint=_sha(
            source_mapping_verification.get("mapping_fingerprint"), "source_mapping"
        ),
        sla_contract_fingerprint=_sha(
            activation.sla_contract_fingerprint, "sla_contract"
        ),
        quantity_contract_fingerprint=_sha(
            activation.quantity_contract_fingerprint, "quantity_contract"
        ),
        approval_reference=approval,
        reviewer=reviewer_name,
        approved_for_registry_review=True,
        executable=False,
    )
