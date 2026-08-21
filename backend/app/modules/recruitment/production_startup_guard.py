"""Fail-closed production startup contract for Hiring authorities.

The future e-Devlet institutional M2M contract is optional external capacity.
Every repository/infrastructure-controlled Hiring authority, including governed
recruitment orchestration, audit fencing, interview scheduling, lifecycle
approval/offboarding, and anonymous capability abuse protection, must be ready.
"""
from __future__ import annotations

import os

from app.modules.workforce import persistence
from .candidate_evidence_storage import EvidenceStorageError, S3KmsEnvelopeEvidenceStore
from .public_capability_guard import PublicCapabilityGuardError, preflight as public_capability_preflight
from .scanner_database_authority import ScannerDatabaseAuthorityError, live_preflight as scanner_db_preflight
from .scanner_key_authority import AwsKmsHmacKeyAuthority, ScannerKeyAuthorityError


class RecruitmentProductionStartupError(RuntimeError):
    pass


REQUIRED_RECRUITMENT_SCHEMA_VERSION = 47


def _production() -> bool:
    return os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"


def assert_recruitment_production_ready() -> None:
    if not _production():
        return
    if not persistence.ENABLED:
        raise RecruitmentProductionStartupError("Production Hiring PostgreSQL olmadan başlatılamaz.")
    schema = persistence.schema_version() or 0
    if schema < REQUIRED_RECRUITMENT_SCHEMA_VERSION:
        raise RecruitmentProductionStartupError(
            f"Production Hiring V{REQUIRED_RECRUITMENT_SCHEMA_VERSION} PostgreSQL authority gerektiriyor; mevcut V{schema}."
        )
    if os.getenv("RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE", "").strip().lower() != "postgres":
        raise RecruitmentProductionStartupError("Production candidate upload authority PostgreSQL modunda olmalıdır.")
    if os.getenv("RECRUITMENT_EVIDENCE_STORAGE_MODE", "").strip().lower() != "s3-kms-envelope":
        raise RecruitmentProductionStartupError("Production recruitment evidence yalnız S3/KMS envelope storage kullanabilir.")
    try:
        S3KmsEnvelopeEvidenceStore.from_environment()
        AwsKmsHmacKeyAuthority.from_environment()
        scanner_db_preflight()
        public_capability_preflight()
    except (
        EvidenceStorageError,
        ScannerKeyAuthorityError,
        ScannerDatabaseAuthorityError,
        PublicCapabilityGuardError,
    ) as error:
        raise RecruitmentProductionStartupError(str(error)) from error
