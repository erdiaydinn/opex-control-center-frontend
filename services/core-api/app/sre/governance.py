"""Master 45-48 SRE acceptance and external evidence authority."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

EvidenceClass = Literal[
    "REPOSITORY",
    "SYNTHETIC",
    "MANAGED_STAGING",
    "REAL_ENVIRONMENT",
    "REAL_MEDIA_ENVIRONMENT",
]

_EXTERNAL_EVIDENCE = frozenset(
    {"MANAGED_STAGING", "REAL_ENVIRONMENT", "REAL_MEDIA_ENVIRONMENT"}
)


@dataclass(frozen=True)
class AcceptanceEvidence:
    key: str
    evidence_class: EvidenceClass
    environment: str
    measured: bool
    provenance: str


def external_gate_satisfied(evidence: AcceptanceEvidence) -> bool:
    """Repository/synthetic evidence can never satisfy an external acceptance gate."""

    return (
        evidence.evidence_class in _EXTERNAL_EVIDENCE
        and evidence.measured
        and bool(evidence.provenance.strip())
        and bool(evidence.environment.strip())
    )


def production_shape_evidence_satisfied(
    profile: dict[str, object],
    evidence: AcceptanceEvidence,
) -> bool:
    if not external_gate_satisfied(evidence):
        return False

    required = str(profile.get("required_evidence", ""))
    if required == "MANAGED_STAGING_LOAD":
        return evidence.evidence_class in _EXTERNAL_EVIDENCE
    if required == "REAL_MEDIA_ENVIRONMENT_LOAD":
        return evidence.evidence_class == "REAL_MEDIA_ENVIRONMENT"
    return False


def load_sre_registry(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported SRE registry schema")

    services = data.get("services", [])
    if not isinstance(services, list):
        raise ValueError("SRE services must be a list")
    keys = [str(item.get("service", "")) for item in services]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate service ownership")

    for item in services:
        if not item.get("owner"):
            raise ValueError("service owner required")
        slo = item.get("slo", {})
        availability = float(slo.get("availability", 0))
        p95_ms = int(slo.get("p95_ms", 0))
        if not 0 < availability <= 1:
            raise ValueError("invalid availability SLO")
        if p95_ms <= 0:
            raise ValueError("invalid p95 latency SLO")

    for test in data.get("production_shape_tests", []):
        if test.get("synthetic_is_sufficient") is not False:
            raise ValueError("production-shape load cannot accept synthetic evidence")
        if test.get("required_evidence") not in {
            "MANAGED_STAGING_LOAD",
            "REAL_MEDIA_ENVIRONMENT_LOAD",
        }:
            raise ValueError("production-shape evidence class is not governed")

    dr = data.get("dr_requirements", {})
    if dr.get("synthetic_is_sufficient") is not False:
        raise ValueError("DR cannot accept synthetic evidence")
    if dr.get("backup_restore") != "MANAGED_STAGING_RESTORE":
        raise ValueError("DR restore environment weakened")
    if dr.get("rpo_rto") != "MEASURED":
        raise ValueError("DR RPO/RTO must be measured")
    return data
