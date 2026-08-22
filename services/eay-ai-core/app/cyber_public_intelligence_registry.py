"""Governed public cyber-intelligence source admission for defensive Jarvis use.

Public Internet intelligence is corroborative evidence. A feed can describe a
vulnerability, advisory, global exploitation signal or IOC, but it cannot prove
EAY exposure or an EAY incident and it never creates execution authority.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

CYBER_PUBLIC_INTELLIGENCE_CONTRACT = "eay-cyber-public-intelligence-registry-v1"


class PublicIntelAuthority(str, Enum):
    VULNERABILITY = "vulnerability"
    VULNERABILITY_ENRICHMENT = "vulnerability_enrichment"
    COORDINATED_DISCLOSURE = "coordinated_disclosure"
    ADVISORY = "advisory"
    IOC = "ioc"
    MALWARE_METADATA = "malware_metadata"
    KNOWN_EXPLOITATION_CORROBORATION = "known_exploitation_corroboration"


class PublicIntelAuthMode(str, Enum):
    NONE = "none"
    PROTECTED_SERVER_SECRET = "protected_server_secret"


class PublicIntelSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_PUBLIC_INTELLIGENCE_CONTRACT
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    official_ref: str = Field(pattern=r"^https://")
    authority: PublicIntelAuthority
    auth_mode: PublicIntelAuthMode = PublicIntelAuthMode.NONE
    maximum_observation_age_seconds: int = Field(gt=0)
    terms_review_required: bool = False
    server_side_only: bool = True
    allowlisted_network_only: bool = True
    read_only_queries_only: bool = True
    sample_download_permitted: bool = False
    indicator_submission_permitted: bool = False
    company_exposure_authority: bool = False
    incident_confirmation_authority: bool = False
    production_mutation_permitted: bool = False
    credential_capture_permitted: bool = False
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def source_is_read_only_and_non_authoritative(self) -> PublicIntelSource:
        if not self.server_side_only or not self.allowlisted_network_only:
            raise ValueError("public_intel_requires_server_side_allowlisted_network")
        if not self.read_only_queries_only:
            raise ValueError("public_intel_queries_must_be_read_only")
        if self.sample_download_permitted or self.indicator_submission_permitted:
            raise ValueError("public_intel_download_or_submission_forbidden")
        if any(
            (
                self.company_exposure_authority,
                self.incident_confirmation_authority,
                self.production_mutation_permitted,
                self.credential_capture_permitted,
                self.exploit_generation_permitted,
                self.execution_authority_granted,
            )
        ):
            raise ValueError("public_intel_never_mints_eay_or_execution_authority")
        return self

    @property
    def fingerprint(self) -> str:
        return _sha256(self.model_dump(mode="json"))


class PublicIntelRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_PUBLIC_INTELLIGENCE_CONTRACT
    registry_id: str = Field(min_length=1)
    sources: tuple[PublicIntelSource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def registry_is_unique(self) -> PublicIntelRegistry:
        source_ids = tuple(source.source_id for source in self.sources)
        refs = tuple(source.official_ref.lower() for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("public_intel_source_ids_must_be_unique")
        if len(refs) != len(set(refs)):
            raise ValueError("public_intel_official_refs_must_be_unique")
        return self

    @property
    def fingerprint(self) -> str:
        return _sha256(self.model_dump(mode="json"))


class PublicIntelAdmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    admitted_read_only: bool
    blockers: tuple[str, ...]
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_exposure_authority: bool = False
    incident_confirmation_authority: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_never_grants_authority(self) -> PublicIntelAdmission:
        if any(
            (
                self.company_exposure_authority,
                self.incident_confirmation_authority,
                self.execution_authority_granted,
            )
        ):
            raise ValueError("public_intel_admission_never_grants_authority")
        if self.admitted_read_only == bool(self.blockers):
            raise ValueError("public_intel_admission_blocker_state_invalid")
        return self


def load_public_intel_registry(path: str | Path) -> PublicIntelRegistry:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return PublicIntelRegistry.model_validate(raw)


def assess_public_intel_source(
    source: PublicIntelSource,
    *,
    terms_review_passed: bool = False,
    protected_secret_configured: bool = False,
    egress_allowlist_verified: bool = False,
) -> PublicIntelAdmission:
    blockers: list[str] = []
    if source.terms_review_required and not terms_review_passed:
        blockers.append("terms_or_commercial_use_review_required")
    if (
        source.auth_mode is PublicIntelAuthMode.PROTECTED_SERVER_SECRET
        and not protected_secret_configured
    ):
        blockers.append("protected_server_secret_required")
    if not egress_allowlist_verified:
        blockers.append("egress_allowlist_verification_required")
    return PublicIntelAdmission(
        source_id=source.source_id,
        admitted_read_only=not blockers,
        blockers=tuple(blockers),
        source_fingerprint=source.fingerprint,
    )


def _sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
