"""Master 35: read-only Orders V2 production-evidence receipt.

This module does not activate production or replace the canonical live-proof
runner. It deterministically summarizes externally obtained evidence so later
KPI/Insight layers can remain fail-closed until every required live proof is
present, reviewed and provenance-bound.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

EvidenceClass = Literal[
    "REPOSITORY",
    "SYNTHETIC",
    "REAL_PRODUCTION_READONLY",
    "REAL_HUMAN_APPROVAL",
]
REQUIRED_EVIDENCE_KEYS = (
    "authorized_readonly_identity",
    "information_schema_observation",
    "entity_id_discriminator",
    "cross_tenant_zero_leak",
    "schema_attestation",
    "human_release_deploy_promotion",
)
EXPECTED_EVIDENCE_CLASS = MappingProxyType(
    {
        "authorized_readonly_identity": "REAL_PRODUCTION_READONLY",
        "information_schema_observation": "REAL_PRODUCTION_READONLY",
        "entity_id_discriminator": "REAL_PRODUCTION_READONLY",
        "cross_tenant_zero_leak": "REAL_PRODUCTION_READONLY",
        "schema_attestation": "REAL_PRODUCTION_READONLY",
        "human_release_deploy_promotion": "REAL_HUMAN_APPROVAL",
    }
)


@dataclass(frozen=True)
class ProductionEvidence:
    key: str
    tenant_id: str
    evidence_class: EvidenceClass
    passed: bool
    provenance: str
    approver: str


@dataclass(frozen=True)
class OrdersV2ProductionReceipt:
    tenant_id: str
    ready: bool
    blockers: tuple[str, ...]
    evidence_fingerprint: str
    production_activation_permitted: Literal[False] = False


def _evidence_fingerprint(records: tuple[ProductionEvidence, ...]) -> str:
    payload = [
        {
            "key": record.key,
            "tenant_id": record.tenant_id,
            "evidence_class": record.evidence_class,
            "passed": record.passed,
            "provenance": record.provenance,
            "approver": record.approver,
        }
        for record in sorted(records, key=lambda item: item.key)
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def orders_v2_production_receipt(
    records: tuple[ProductionEvidence, ...],
) -> OrdersV2ProductionReceipt:
    blockers: list[str] = []
    tenants = {
        record.tenant_id.strip() for record in records if record.tenant_id.strip()
    }
    if len(tenants) != 1:
        blockers.append("tenant_identity:ambiguous_or_missing")
        tenant_id = ""
    else:
        tenant_id = next(iter(tenants))

    by_key: dict[str, ProductionEvidence] = {}
    duplicates: set[str] = set()
    for record in records:
        if record.key in by_key:
            duplicates.add(record.key)
        by_key[record.key] = record
    for key in sorted(duplicates):
        blockers.append(f"{key}:duplicate")

    unexpected = sorted(set(by_key) - set(REQUIRED_EVIDENCE_KEYS))
    blockers.extend(f"{key}:unexpected" for key in unexpected)

    for key in REQUIRED_EVIDENCE_KEYS:
        record = by_key.get(key)
        if record is None:
            blockers.append(f"{key}:missing")
            continue
        if tenant_id and record.tenant_id != tenant_id:
            blockers.append(f"{key}:tenant_mismatch")
            continue
        if not record.passed:
            blockers.append(f"{key}:failed")
            continue
        expected_class = EXPECTED_EVIDENCE_CLASS[key]
        if record.evidence_class != expected_class:
            blockers.append(f"{key}:wrong_evidence_class")
            continue
        if not record.provenance.strip() or not record.approver.strip():
            blockers.append(f"{key}:incomplete_provenance")

    return OrdersV2ProductionReceipt(
        tenant_id=tenant_id,
        ready=not blockers,
        blockers=tuple(blockers),
        evidence_fingerprint=_evidence_fingerprint(records),
    )


def orders_v2_production_ready(
    records: tuple[ProductionEvidence, ...],
) -> tuple[bool, tuple[str, ...]]:
    """Compatibility projection for tests; never grants production execution."""

    receipt = orders_v2_production_receipt(records)
    return receipt.ready, receipt.blockers
