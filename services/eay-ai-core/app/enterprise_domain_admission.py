"""Fail-closed admission for evidence-grounded enterprise-domain answers.

Domain registration describes what a specialist answer needs.  This module
proves that one concrete answer has those authorities; it never grants tool or
business execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .enterprise_domain_registry import (
    EnterpriseDomain,
    SourceAuthority,
    require_domain_contract,
)

ENTERPRISE_DOMAIN_ADMISSION_CONTRACT = "eay-enterprise-domain-admission-v1"


class DomainRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DomainEvidence(BaseModel):
    evidence_ref: str = Field(min_length=1)
    authority: SourceAuthority
    observed_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    tenant_id: str | None = None
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative: bool = True

    @model_validator(mode="after")
    def valid_interval(self) -> DomainEvidence:
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("domain_evidence_invalid_interval")
        return self


class DomainAnswerRequest(BaseModel):
    request_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    domain: EnterpriseDomain
    as_of: datetime
    risk: DomainRisk
    contains_employee_data: bool = False
    deterministic_result_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    independent_critic_receipt_ref: str | None = None
    human_approval_ref: str | None = None


class DomainAdmission(BaseModel):
    contract: str = ENTERPRISE_DOMAIN_ADMISSION_CONTRACT
    request_id: str
    domain: EnterpriseDomain
    decision_ready: bool
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    admission_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def advisory_only(self) -> DomainAdmission:
        if self.execution_authority_granted:
            raise ValueError("domain_admission_never_grants_execution_authority")
        if self.decision_ready and self.blockers:
            raise ValueError("domain_admission_cannot_ignore_blockers")
        return self


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("domain_admission_timezone_required")
    return value.astimezone(UTC)


def admit_domain_answer(
    request: DomainAnswerRequest,
    evidence: tuple[DomainEvidence, ...],
) -> DomainAdmission:
    contract = require_domain_contract(request.domain)
    as_of = _utc(request.as_of)
    blockers: list[str] = []
    accepted: list[DomainEvidence] = []

    seen_refs: set[str] = set()
    for item in evidence:
        if item.evidence_ref in seen_refs:
            blockers.append("duplicate_evidence_ref")
            continue
        seen_refs.add(item.evidence_ref)
        observed_at = _utc(item.observed_at)
        valid_from = _utc(item.valid_from) if item.valid_from else None
        valid_until = _utc(item.valid_until) if item.valid_until else None
        if not item.authoritative:
            blockers.append(f"evidence_not_authoritative:{item.evidence_ref}")
        elif observed_at > as_of:
            blockers.append(f"future_evidence:{item.evidence_ref}")
        elif valid_from and as_of < valid_from:
            blockers.append(f"evidence_not_yet_effective:{item.evidence_ref}")
        elif valid_until and as_of > valid_until:
            blockers.append(f"evidence_expired:{item.evidence_ref}")
        elif item.tenant_id not in {None, request.tenant_id}:
            blockers.append(f"cross_tenant_evidence:{item.evidence_ref}")
        else:
            accepted.append(item)

    present = {item.authority for item in accepted}
    for authority in contract.required_authorities:
        if authority not in present:
            blockers.append(f"required_authority_missing:{authority.value}")

    if contract.temporal_resolution_required and not evidence:
        blockers.append("temporal_evidence_required")
    if contract.deterministic_calculation_required and not request.deterministic_result_fingerprint:
        blockers.append("deterministic_result_evidence_required")
    if request.contains_employee_data and not contract.employee_personalization_allowed:
        blockers.append("employee_personalization_forbidden_for_domain")
    if request.risk in {DomainRisk.HIGH, DomainRisk.CRITICAL} and not request.independent_critic_receipt_ref:
        blockers.append("independent_domain_critic_required")
    if request.risk is DomainRisk.CRITICAL and not request.human_approval_ref:
        blockers.append("critical_domain_human_approval_required")

    blockers = list(dict.fromkeys(blockers))
    refs = tuple(sorted(item.evidence_ref for item in accepted))
    payload = {
        "contract": ENTERPRISE_DOMAIN_ADMISSION_CONTRACT,
        "request_id": request.request_id,
        "tenant_id": request.tenant_id,
        "domain": request.domain.value,
        "as_of": as_of.isoformat(),
        "risk": request.risk.value,
        "evidence": [
            {"ref": item.evidence_ref, "authority": item.authority.value, "fingerprint": item.source_fingerprint}
            for item in sorted(accepted, key=lambda value: value.evidence_ref)
        ],
        "blockers": blockers,
        "deterministic_result_fingerprint": request.deterministic_result_fingerprint,
        "critic": request.independent_critic_receipt_ref,
        "approval": request.human_approval_ref,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return DomainAdmission(
        request_id=request.request_id,
        domain=request.domain,
        decision_ready=not blockers,
        blockers=tuple(blockers),
        evidence_refs=refs,
        admission_fingerprint=fingerprint,
    )
