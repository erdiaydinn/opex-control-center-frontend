"""Master 49-51 real identity, physical device, and real-data acceptance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

EnvironmentClass = Literal[
    "CORPORATE_REAL",
    "MANAGED_STAGING",
    "PHYSICAL_DEVICE",
    "REAL_BUILD",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CorporateIdentityAcceptance:
    environment_class: EnvironmentClass
    issuer: str
    tenant: str
    employee_id_claim: str
    warehouse_scope_claim: str
    stale_token_rejected: bool
    exit_revocation_passed: bool
    workload_identity_passed: bool
    service_account_passed: bool
    provenance: str
    approver: str


def corporate_identity_accepted(evidence: CorporateIdentityAcceptance) -> bool:
    required_text = (
        evidence.issuer,
        evidence.tenant,
        evidence.employee_id_claim,
        evidence.warehouse_scope_claim,
        evidence.provenance,
        evidence.approver,
    )
    return (
        evidence.environment_class == "CORPORATE_REAL"
        and all(value.strip() for value in required_text)
        and evidence.stale_token_rejected
        and evidence.exit_revocation_passed
        and evidence.workload_identity_passed
        and evidence.service_account_passed
    )


@dataclass(frozen=True)
class PhysicalDeviceAcceptance:
    environment_class: EnvironmentClass
    platform: str
    device_model: str
    mdm_identity: str
    integrity_provider: str
    integrity_passed: bool
    lost_replace_passed: bool
    offline_reconnect_passed: bool
    provenance: str
    approver: str


def physical_device_accepted(evidence: PhysicalDeviceAcceptance) -> bool:
    required_text = (
        evidence.platform,
        evidence.device_model,
        evidence.mdm_identity,
        evidence.integrity_provider,
        evidence.provenance,
        evidence.approver,
    )
    return (
        evidence.environment_class == "PHYSICAL_DEVICE"
        and all(value.strip() for value in required_text)
        and evidence.integrity_passed
        and evidence.lost_replace_passed
        and evidence.offline_reconnect_passed
    )


@dataclass(frozen=True)
class RealDataAcceptance:
    environment_class: EnvironmentClass
    dataset_key: str
    source_hash: str
    source_rows: int
    reconciled_rows: int
    mismatch_rows: int
    provenance: str
    approver: str


def real_data_accepted(evidence: RealDataAcceptance) -> bool:
    return (
        evidence.environment_class in {"MANAGED_STAGING", "CORPORATE_REAL"}
        and _SHA256.fullmatch(evidence.source_hash.lower()) is not None
        and evidence.source_rows > 0
        and evidence.reconciled_rows == evidence.source_rows
        and evidence.mismatch_rows == 0
        and bool(
            evidence.dataset_key.strip()
            and evidence.provenance.strip()
            and evidence.approver.strip()
        )
    )
