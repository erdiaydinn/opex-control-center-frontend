from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.repository_intelligence import RepositoryRegistry

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
    def copyleft_is_never_adoption_authority(self) -> "ArchiveProvenanceRecord":
        spdx = self.license.spdx.upper()
        if spdx.startswith(("AGPL-", "GPL-", "LGPL-")) and self.decision == "ADOPT":
            raise ValueError("copyleft_archive_cannot_be_adoption_authority")
        return self


class ArchiveProvenanceLedger(BaseModel):
    schema_version: Literal[1]
    updated_at: str = Field(min_length=10)
    records: list[ArchiveProvenanceRecord]

    @model_validator(mode="after")
    def no_silent_duplicate_or_shadow_record(self) -> "ArchiveProvenanceLedger":
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


def _verified_supplied_archive_ids(registry: RepositoryRegistry) -> set[str]:
    required: set[str] = set()
    for entry in registry.entries:
        if (
            entry["classification"] == "IMPORTED"
            and entry["identity_status"] == "VERIFIED"
            and entry["relation"] == "supplied-archive-to-canonical-upstream"
        ):
            required.add(entry["id"])
    return required


def validate_archive_provenance_against_registry(
    registry: RepositoryRegistry,
    ledger: ArchiveProvenanceLedger,
) -> None:
    """Bind promotion-grade supplied-archive evidence to the canonical registry.

    The ledger may prove identity but may never widen policy. Every verified imported supplied
    archive in the registry must retain a matching evidence record; unresolved entries cannot
    acquire authority merely by appearing in this ledger.
    """
    registry_entries = {entry["id"]: entry for entry in registry.entries}
    ledger_ids = {record.registry_entry_id for record in ledger.records}
    missing = _verified_supplied_archive_ids(registry) - ledger_ids
    if missing:
        raise ValueError(f"archive_provenance_verified_registry_entries_missing:{sorted(missing)}")

    for record in ledger.records:
        entry = registry_entries.get(record.registry_entry_id)
        if entry is None:
            raise ValueError(f"archive_provenance_registry_entry_missing:{record.registry_entry_id}")
        if entry["classification"] != "IMPORTED":
            raise ValueError(f"archive_provenance_requires_imported_entry:{record.registry_entry_id}")
        if entry["identity_status"] != "VERIFIED":
            raise ValueError(f"archive_provenance_cannot_promote_unresolved_entry:{record.registry_entry_id}")
        if record.archive.casefold() not in entry["source_locator"].casefold():
            raise ValueError(f"archive_provenance_source_locator_mismatch:{record.registry_entry_id}")
        if entry["repository"] != record.canonical_repository:
            raise ValueError(f"archive_provenance_repository_mismatch:{record.registry_entry_id}")
        if entry["canonical_upstream"] != record.canonical_repository:
            raise ValueError(f"archive_provenance_upstream_mismatch:{record.registry_entry_id}")
        if entry["last_reviewed_ref"] != record.ref:
            raise ValueError(f"archive_provenance_review_ref_mismatch:{record.registry_entry_id}")
        if entry["last_reviewed_sha"] != record.commit_sha:
            raise ValueError(f"archive_provenance_review_commit_mismatch:{record.registry_entry_id}")
        if entry["license"] != {"spdx": record.license.spdx, "status": "VERIFIED"}:
            raise ValueError(f"archive_provenance_license_mismatch:{record.registry_entry_id}")
        if entry["decision"] != record.decision:
            raise ValueError(f"archive_provenance_decision_mismatch:{record.registry_entry_id}")

        spdx = record.license.spdx.upper()
        if spdx.startswith(("AGPL-", "GPL-", "LGPL-")) and entry["decision"] not in {
            "REFERENCE",
            "REJECT",
        }:
            raise ValueError(f"copyleft_archive_registry_decision_too_permissive:{record.registry_entry_id}")


def verified_archive_registry_ids(
    registry: RepositoryRegistry,
    ledger: ArchiveProvenanceLedger,
) -> tuple[str, ...]:
    validate_archive_provenance_against_registry(registry, ledger)
    return tuple(record.registry_entry_id for record in ledger.records)
