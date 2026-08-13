from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .repository_intelligence import RepositoryRegistry

DEFAULT_ARCHIVE_PROVENANCE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "repository_archive_provenance.json"
)

ExactArchiveMatch = Literal["EXACT_RECOMPUTED_GIT_TREE"]
ArchiveDecision = Literal["REFERENCE", "WATCH", "ADOPT", "REJECT"]


class ArchiveLicense(BaseModel):
    spdx: str = Field(min_length=1)
    status: Literal["VERIFIED"]


class ArchiveProvenanceRecord(BaseModel):
    registry_entry_id: str = Field(min_length=1)
    archive: str = Field(min_length=1)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    ref: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    readme_blob_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    license_blob_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    match: ExactArchiveMatch
    license: ArchiveLicense
    commercial_use: str = Field(min_length=1)
    decision: ArchiveDecision

    @model_validator(mode="after")
    def copyleft_is_never_adoption_authority(self):
        if self.license.spdx.upper().startswith(("AGPL-", "GPL-", "LGPL-")) and self.decision == "ADOPT":
            raise ValueError("copyleft_archive_cannot_be_adoption_authority")
        return self


class ArchiveProvenanceLedger(BaseModel):
    schema_version: Literal[1]
    updated_at: str = Field(min_length=10)
    records: list[ArchiveProvenanceRecord]

    @model_validator(mode="after")
    def no_silent_duplicate_or_shadow_record(self):
        ids = [record.registry_entry_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_archive_registry_entry_id")
        archives = [record.archive.casefold() for record in self.records]
        if len(archives) != len(set(archives)):
            raise ValueError("duplicate_archive_provenance_record")
        if not self.records:
            raise ValueError("archive_provenance_records_required")
        return self

    def by_registry_entry_id(self) -> dict[str, ArchiveProvenanceRecord]:
        return {record.registry_entry_id: record for record in self.records}

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_policy_token(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def load_archive_provenance_text(source_text: str) -> ArchiveProvenanceLedger:
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise ValueError("archive_provenance_invalid_json") from exc
    return ArchiveProvenanceLedger.model_validate(payload)


def load_archive_provenance(
    path: Path = DEFAULT_ARCHIVE_PROVENANCE_PATH,
) -> ArchiveProvenanceLedger:
    return load_archive_provenance_text(path.read_text(encoding="utf-8"))


def validate_archive_provenance_against_registry(
    registry: RepositoryRegistry,
    ledger: ArchiveProvenanceLedger,
) -> None:
    """Require exact archive evidence to agree with the canonical registry fail closed.

    The ledger is evidence, not a license bypass. A record can promote identity only when the
    supplied archive was recomputed to the exact Git tree and the resulting registry state keeps
    the external source inside its reviewed commercial-use decision.
    """
    registry_entries = registry.by_id()
    for record in ledger.records:
        entry = registry_entries.get(record.registry_entry_id)
        if entry is None:
            raise ValueError(f"archive_provenance_registry_entry_missing:{record.registry_entry_id}")
        if entry.classification != "IMPORTED":
            raise ValueError(f"archive_provenance_requires_imported_entry:{record.registry_entry_id}")
        if not entry.source_artifact or record.archive.casefold() not in entry.source_artifact.casefold():
            raise ValueError(f"archive_provenance_source_artifact_mismatch:{record.registry_entry_id}")
        if entry.identity != record.canonical_repository:
            raise ValueError(f"archive_provenance_repository_mismatch:{record.registry_entry_id}")
        if entry.canonical_upstream != record.canonical_repository:
            raise ValueError(f"archive_provenance_upstream_mismatch:{record.registry_entry_id}")
        if entry.review.ref != record.ref or entry.review.commit != record.commit_sha:
            raise ValueError(f"archive_provenance_review_revision_mismatch:{record.registry_entry_id}")
        if entry.review.license != record.license.spdx:
            raise ValueError(f"archive_provenance_license_mismatch:{record.registry_entry_id}")
        if _normalize_policy_token(entry.review.commercial_use) != _normalize_policy_token(record.commercial_use):
            raise ValueError(f"archive_provenance_commercial_use_mismatch:{record.registry_entry_id}")
        if entry.decision != record.decision.lower():
            raise ValueError(f"archive_provenance_decision_mismatch:{record.registry_entry_id}")

        if record.match != "EXACT_RECOMPUTED_GIT_TREE" or record.license.status != "VERIFIED":
            raise ValueError(f"archive_provenance_not_promotion_grade:{record.registry_entry_id}")

        spdx = record.license.spdx.upper()
        if spdx.startswith(("AGPL-", "GPL-", "LGPL-")) and entry.decision not in {
            "reference",
            "reject",
        }:
            raise ValueError(f"copyleft_archive_registry_decision_too_permissive:{record.registry_entry_id}")


def verified_archive_registry_ids(
    registry: RepositoryRegistry,
    ledger: ArchiveProvenanceLedger,
) -> tuple[str, ...]:
    validate_archive_provenance_against_registry(registry, ledger)
    return tuple(record.registry_entry_id for record in ledger.records)
