from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_LICENSE_BOUNDARY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "repository_license_boundary_evidence.json"
)


class RepositoryLicenseBoundaryError(ValueError):
    pass


class MixedLicenseRecord(BaseModel):
    repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    ref: str = Field(min_length=1)
    commit_sha: str
    tree_sha: str
    license_boundary: str
    core_license: str
    restricted_paths: list[str]
    restricted_license: str
    capabilities: list[str]
    decision: str
    commercial_use_policy: str
    source_license_blob_sha: str
    restricted_license_blob_sha: str

    @model_validator(mode="after")
    def validate_boundary(self):
        if not SHA40.fullmatch(self.commit_sha) or not SHA40.fullmatch(self.tree_sha):
            raise ValueError("mixed_license_invalid_git_identity")
        if not SHA40.fullmatch(self.source_license_blob_sha) or not SHA40.fullmatch(
            self.restricted_license_blob_sha
        ):
            raise ValueError("mixed_license_invalid_license_blob_identity")
        if self.license_boundary != "MIXED":
            raise ValueError("mixed_license_boundary_must_be_explicit")
        if self.core_license != "MIT":
            raise ValueError("mixed_license_core_license_not_reviewed")
        if self.decision not in {"REFERENCE", "WATCH"}:
            raise ValueError("mixed_license_repository_cannot_be_adoption_authority")
        if not self.restricted_paths or any(not path.endswith("/") for path in self.restricted_paths):
            raise ValueError("mixed_license_restricted_paths_required")
        if "REQUIRE_SEPARATE_LICENSE" not in self.commercial_use_policy:
            raise ValueError("mixed_license_commercial_boundary_missing")
        if not self.capabilities:
            raise ValueError("mixed_license_capability_mapping_required")
        return self


class RepositoryLicenseBoundaryLedger(BaseModel):
    schema_version: int
    observed_at: str = Field(min_length=10)
    records: list[MixedLicenseRecord]

    @model_validator(mode="after")
    def validate_ledger(self):
        if self.schema_version != 1:
            raise ValueError("unsupported_repository_license_boundary_schema")
        repos = [record.repository.casefold() for record in self.records]
        if not repos or len(repos) != len(set(repos)):
            raise ValueError("repository_license_boundary_duplicate_or_empty")
        return self


def load_repository_license_boundary_text(source_text: str) -> RepositoryLicenseBoundaryLedger:
    try:
        payload: Any = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise RepositoryLicenseBoundaryError("repository_license_boundary_invalid_json") from exc
    try:
        return RepositoryLicenseBoundaryLedger.model_validate(payload)
    except ValueError as exc:
        raise RepositoryLicenseBoundaryError(str(exc)) from exc


def load_repository_license_boundary(
    path: Path = DEFAULT_LICENSE_BOUNDARY_PATH,
) -> RepositoryLicenseBoundaryLedger:
    return load_repository_license_boundary_text(path.read_text(encoding="utf-8"))
