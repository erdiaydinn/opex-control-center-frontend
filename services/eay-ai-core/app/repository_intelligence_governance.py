from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.repository_intelligence import (
    RepositoryRegistry,
    RepositoryRegistryError,
    load_repository_registry,
)


def validate_repository_registry_governance(
    registry: RepositoryRegistry,
) -> RepositoryRegistry:
    for entry in registry.entries:
        identity_status = entry["identity_status"]
        license_info = entry["license"]
        classification = entry["classification"]

        if identity_status == "UNRESOLVED":
            if entry["repository"] is not None or entry["canonical_upstream"] is not None:
                raise RepositoryRegistryError(
                    f"unresolved entry {entry['id']} cannot assert repository identity"
                )
            if entry["decision"] != "PENDING":
                raise RepositoryRegistryError(
                    f"unresolved entry {entry['id']} must remain PENDING"
                )
            if license_info != {"spdx": None, "status": "PENDING"}:
                raise RepositoryRegistryError(
                    f"unresolved entry {entry['id']} must keep license PENDING"
                )

        if classification == "OWN":
            if license_info["status"] != "OWN_INTERNAL_POLICY":
                raise RepositoryRegistryError(
                    f"OWN entry {entry['id']} requires OWN_INTERNAL_POLICY"
                )
        elif license_info["status"] == "OWN_INTERNAL_POLICY":
            raise RepositoryRegistryError(
                f"external entry {entry['id']} cannot use OWN_INTERNAL_POLICY"
            )

        if license_info["status"] == "VERIFIED" and not license_info["spdx"]:
            raise RepositoryRegistryError(
                f"verified license for {entry['id']} requires SPDX"
            )

    return registry


def _require_hex(value: Any, length: int, field: str, record_id: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise RepositoryRegistryError(f"invalid {field} for {record_id}")
    if any(char not in "0123456789abcdef" for char in value.lower()):
        raise RepositoryRegistryError(f"invalid {field} for {record_id}")
    return value


def _verified_supplied_archive_ids(registry: RepositoryRegistry) -> set[str]:
    """Return registry identities whose supplied archives are asserted as verified truth."""
    required: set[str] = set()
    for entry in registry.entries:
        if entry["classification"] != "IMPORTED" or entry["identity_status"] != "VERIFIED":
            continue
        locator = entry["source_locator"]
        if isinstance(locator, str) and ".zip" in locator.casefold():
            required.add(entry["id"])
    return required


def validate_archive_provenance_governance(
    registry: RepositoryRegistry,
    provenance_payload: dict[str, Any],
) -> None:
    """Require promotion-grade archive evidence to be exact, consistent, and complete.

    Archive provenance is evidence, never an authority override. Records must represent an
    exact recomputed Git tree and bind the supplied archive to the same repository, upstream,
    reviewed revision, SPDX license and decision already carried by the governed registry.
    Every verified IMPORTED registry identity sourced from a supplied ZIP must have exactly one
    ledger record, preventing deletion of evidence while leaving a verified identity behind.
    """
    if provenance_payload.get("schema_version") != 1:
        raise RepositoryRegistryError("unsupported archive provenance schema_version")
    records = provenance_payload.get("records")
    if not isinstance(records, list) or not records:
        raise RepositoryRegistryError("archive provenance records are required")

    by_id = registry.by_id()
    assert isinstance(by_id, dict)
    seen_ids: set[str] = set()
    seen_archives: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            raise RepositoryRegistryError("archive provenance records must be objects")
        record_id = record.get("registry_entry_id")
        archive = record.get("archive")
        if not isinstance(record_id, str) or not record_id:
            raise RepositoryRegistryError("archive provenance registry_entry_id is required")
        if not isinstance(archive, str) or not archive:
            raise RepositoryRegistryError(f"archive provenance archive is required for {record_id}")
        archive_key = archive.casefold()
        if record_id in seen_ids or archive_key in seen_archives:
            raise RepositoryRegistryError("duplicate archive provenance record")
        seen_ids.add(record_id)
        seen_archives.add(archive_key)

        entry = by_id.get(record_id)
        if entry is None:
            raise RepositoryRegistryError(f"archive provenance entry missing from registry: {record_id}")
        if entry["classification"] != "IMPORTED" or entry["identity_status"] != "VERIFIED":
            raise RepositoryRegistryError(f"archive provenance requires verified IMPORTED entry: {record_id}")
        if record.get("match") != "EXACT_RECOMPUTED_GIT_TREE":
            raise RepositoryRegistryError(f"archive provenance is not promotion-grade: {record_id}")

        _require_hex(record.get("archive_sha256"), 64, "archive_sha256", record_id)
        _require_hex(record.get("commit_sha"), 40, "commit_sha", record_id)
        _require_hex(record.get("tree_sha"), 40, "tree_sha", record_id)
        _require_hex(record.get("readme_blob_sha"), 40, "readme_blob_sha", record_id)
        _require_hex(record.get("license_blob_sha"), 40, "license_blob_sha", record_id)

        repository = record.get("canonical_repository")
        if repository != entry["repository"] or repository != entry["canonical_upstream"]:
            raise RepositoryRegistryError(f"archive provenance repository mismatch: {record_id}")
        if archive_key not in entry["source_locator"].casefold():
            raise RepositoryRegistryError(f"archive provenance source mismatch: {record_id}")
        if record.get("ref") != entry["last_reviewed_ref"]:
            raise RepositoryRegistryError(f"archive provenance ref mismatch: {record_id}")
        if record.get("commit_sha") != entry["last_reviewed_sha"]:
            raise RepositoryRegistryError(f"archive provenance commit mismatch: {record_id}")

        license_info = record.get("license")
        expected_license = entry["license"]
        if license_info != expected_license or expected_license.get("status") != "VERIFIED":
            raise RepositoryRegistryError(f"archive provenance license mismatch: {record_id}")
        if record.get("decision") != entry["decision"]:
            raise RepositoryRegistryError(f"archive provenance decision mismatch: {record_id}")

        spdx = expected_license.get("spdx") or ""
        if spdx.upper().startswith(("AGPL-", "GPL-", "LGPL-")) and entry["decision"] not in {
            "REFERENCE",
            "REJECT",
        }:
            raise RepositoryRegistryError(f"copyleft archive decision too permissive: {record_id}")

    missing = _verified_supplied_archive_ids(registry) - seen_ids
    if missing:
        raise RepositoryRegistryError(
            "verified supplied archive provenance missing: " + ", ".join(sorted(missing))
        )


def load_governed_repository_registry(path: str | Path) -> RepositoryRegistry:
    return validate_repository_registry_governance(load_repository_registry(path))


def validate_archive_provenance_file(
    registry: RepositoryRegistry,
    path: str | Path,
) -> None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RepositoryRegistryError("archive provenance is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RepositoryRegistryError("archive provenance must be a JSON object")
    validate_archive_provenance_governance(registry, payload)
