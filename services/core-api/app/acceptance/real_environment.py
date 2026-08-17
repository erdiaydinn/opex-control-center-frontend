from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EnvironmentClass = Literal['CORPORATE_REAL', 'MANAGED_STAGING', 'PHYSICAL_DEVICE', 'REAL_BUILD']


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


def corporate_identity_accepted(e: CorporateIdentityAcceptance) -> bool:
    return (
        e.environment_class == 'CORPORATE_REAL'
        and all((e.issuer.strip(), e.tenant.strip(), e.employee_id_claim.strip(), e.warehouse_scope_claim.strip(), e.provenance.strip(), e.approver.strip()))
        and e.stale_token_rejected and e.exit_revocation_passed and e.workload_identity_passed and e.service_account_passed
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


def physical_device_accepted(e: PhysicalDeviceAcceptance) -> bool:
    return (
        e.environment_class == 'PHYSICAL_DEVICE'
        and all((e.platform.strip(), e.device_model.strip(), e.mdm_identity.strip(), e.integrity_provider.strip(), e.provenance.strip(), e.approver.strip()))
        and e.integrity_passed and e.lost_replace_passed and e.offline_reconnect_passed
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


def real_data_accepted(e: RealDataAcceptance) -> bool:
    return (
        e.environment_class in {'MANAGED_STAGING', 'CORPORATE_REAL'}
        and len(e.source_hash) == 64
        and e.source_rows > 0
        and e.reconciled_rows == e.source_rows
        and e.mismatch_rows == 0
        and bool(e.dataset_key.strip() and e.provenance.strip() and e.approver.strip())
    )
