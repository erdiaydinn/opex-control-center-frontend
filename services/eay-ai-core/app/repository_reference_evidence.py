from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReferenceLicense(BaseModel):
    spdx: str = Field(min_length=1)
    status: Literal["VERIFIED_FROM_UPSTREAM"]


class ReferenceProvenance(BaseModel):
    commit_source: str = Field(min_length=1)
    license_source: str = Field(min_length=1)
    supplied_archive_match: Literal["NOT_APPLICABLE"]
    registry_promotion: Literal["PENDING_CANONICAL_REGISTRY_REVIEW"]


class RepositoryReferenceEvidence(BaseModel):
    schema_version: Literal[1]
    observed_at: str = Field(min_length=10)
    authority: Literal["REFERENCE_ONLY"]
    repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    canonical_upstream: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    ref: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: ReferenceLicense
    capabilities: list[str] = Field(min_length=1)
    decision: Literal["WATCH", "REFERENCE"]
    commercial_use: str = Field(min_length=1)
    security_relevance: str = Field(min_length=1)
    provenance: ReferenceProvenance

    @model_validator(mode="after")
    def reference_evidence_cannot_claim_identity_or_archive_authority(self):
        if self.repository != self.canonical_upstream:
            raise ValueError("reference_repository_upstream_mismatch")
        if self.authority != "REFERENCE_ONLY":
            raise ValueError("reference_authority_required")
        return self


def load_repository_reference_evidence_text(source_text: str) -> RepositoryReferenceEvidence:
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise ValueError("repository_reference_evidence_invalid_json") from exc
    return RepositoryReferenceEvidence.model_validate(payload)


def load_repository_reference_evidence(path: str | Path) -> RepositoryReferenceEvidence:
    return load_repository_reference_evidence_text(Path(path).read_text(encoding="utf-8"))
