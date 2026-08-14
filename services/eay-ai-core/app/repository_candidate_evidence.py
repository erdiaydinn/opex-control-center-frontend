from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository_intelligence import RepositoryRegistry, RepositoryRegistryError

DEFAULT_CANDIDATE_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "repository_intelligence_candidate_evidence.json"
)

_ALLOWED_MATCH_STATUS = {
    "NOT_VERIFIED",
    "NO_CANDIDATE_FOUND",
}
_ALLOWED_PROMOTION_DECISIONS = {"REFERENCE", "WATCH", "ADOPT", "REJECT"}
_COPYLEFT_PREFIXES = ("AGPL-", "GPL-", "LGPL-")


def _validate_sha(value: Any, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or len(value) != 40 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise RepositoryRegistryError(f"candidate evidence {field} must be an exact lowercase Git SHA-1")


def _validate_sha256(value: Any, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise RepositoryRegistryError(f"candidate evidence {field} must be an exact lowercase SHA-256")


def validate_candidate_evidence(
    registry: RepositoryRegistry,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise RepositoryRegistryError("unsupported candidate evidence schema_version")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RepositoryRegistryError("candidate evidence requires a non-empty candidates list")

    registry_by_id = registry.by_id()
    seen_entries: set[str] = set()
    seen_archives: set[str] = set()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise RepositoryRegistryError("candidate evidence entries must be objects")

        entry_id = candidate.get("registry_entry_id")
        archive = candidate.get("archive")
        if not isinstance(entry_id, str) or not entry_id:
            raise RepositoryRegistryError("candidate evidence registry_entry_id is required")
        if entry_id in seen_entries:
            raise RepositoryRegistryError(f"duplicate candidate evidence entry: {entry_id}")
        seen_entries.add(entry_id)

        if not isinstance(archive, str) or not archive:
            raise RepositoryRegistryError(f"candidate evidence archive is required for {entry_id}")
        archive_key = archive.casefold()
        if archive_key in seen_archives:
            raise RepositoryRegistryError(f"duplicate candidate evidence archive: {archive}")
        seen_archives.add(archive_key)

        entry = registry_by_id.get(entry_id)
        if entry is None:
            raise RepositoryRegistryError(f"candidate evidence references unknown registry entry: {entry_id}")
        if entry.classification != "IMPORTED":
            raise RepositoryRegistryError(f"candidate evidence requires IMPORTED registry entry: {entry_id}")
        if entry.identity is not None or entry.canonical_upstream is not None:
            raise RepositoryRegistryError(f"candidate evidence cannot target resolved registry entry: {entry_id}")
        if entry.decision != "PENDING" or entry.review.license != "unresolved":
            raise RepositoryRegistryError(f"candidate evidence target must remain unresolved/PENDING: {entry_id}")
        if archive.casefold() not in entry["source_locator"].casefold():
            raise RepositoryRegistryError(f"candidate evidence archive does not match registry source: {entry_id}")

        match_status = candidate.get("archive_match_status")
        if match_status not in _ALLOWED_MATCH_STATUS:
            raise RepositoryRegistryError(
                f"candidate evidence may not claim archive verification before promotion-grade provenance: {entry_id}"
            )
        promotion_status = candidate.get("promotion_status")
        if not isinstance(promotion_status, str) or not promotion_status.startswith("BLOCKED_"):
            raise RepositoryRegistryError(f"candidate evidence must remain promotion-blocked: {entry_id}")

        decision_if_matched = candidate.get("decision_if_matched")
        if decision_if_matched not in _ALLOWED_PROMOTION_DECISIONS:
            raise RepositoryRegistryError(f"candidate evidence requires reviewed decision_if_matched: {entry_id}")

        repository = candidate.get("candidate_repository")
        default_branch = candidate.get("candidate_default_branch")
        head_sha = candidate.get("candidate_head_sha")
        tree_sha = candidate.get("candidate_tree_sha")
        license_spdx = candidate.get("candidate_license_spdx")

        _validate_sha(head_sha, "candidate_head_sha")
        _validate_sha(tree_sha, "candidate_tree_sha")

        if repository is None:
            if any(value is not None for value in (default_branch, head_sha, tree_sha, license_spdx)):
                raise RepositoryRegistryError(f"candidate identity fields require candidate_repository: {entry_id}")
            if match_status != "NO_CANDIDATE_FOUND":
                raise RepositoryRegistryError(f"missing candidate repository must use NO_CANDIDATE_FOUND: {entry_id}")
        else:
            if not isinstance(repository, str) or repository.count("/") != 1:
                raise RepositoryRegistryError(f"candidate repository must be exact owner/repo: {entry_id}")
            if not all(isinstance(value, str) and value for value in (default_branch, head_sha, tree_sha)):
                raise RepositoryRegistryError(f"candidate repository requires branch/head/tree evidence: {entry_id}")
            if match_status != "NOT_VERIFIED":
                raise RepositoryRegistryError(f"repository candidate must remain NOT_VERIFIED: {entry_id}")
            if license_spdx is not None and not isinstance(license_spdx, str):
                raise RepositoryRegistryError(f"candidate license SPDX must be a string when present: {entry_id}")

    return payload


def build_archive_match_promotion_proposal(
    registry: RepositoryRegistry,
    candidate_payload: dict[str, Any],
    archive_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build review evidence without mutating the canonical registry.

    Candidate discovery is never enough to resolve a supplied archive. This boundary requires
    exact recomputed Git-tree evidence and emits a human-review proposal only. The caller still
    cannot mutate the registry through this function.
    """

    validate_candidate_evidence(registry, candidate_payload)

    required = {
        "registry_entry_id",
        "archive",
        "archive_sha256",
        "canonical_repository",
        "ref",
        "commit_sha",
        "tree_sha",
        "license_spdx",
        "match",
    }
    if set(archive_evidence) != required:
        raise RepositoryRegistryError("promotion-grade archive evidence must use the exact reviewed field set")

    entry_id = archive_evidence["registry_entry_id"]
    candidate = next(
        (item for item in candidate_payload["candidates"] if item["registry_entry_id"] == entry_id),
        None,
    )
    if candidate is None:
        raise RepositoryRegistryError(f"promotion evidence has no candidate record: {entry_id}")
    if candidate["candidate_repository"] is None:
        raise RepositoryRegistryError(f"promotion evidence requires a discovered repository candidate: {entry_id}")

    if archive_evidence["match"] != "EXACT_RECOMPUTED_GIT_TREE":
        raise RepositoryRegistryError(f"promotion evidence requires exact recomputed Git tree: {entry_id}")

    archive = archive_evidence["archive"]
    repository = archive_evidence["canonical_repository"]
    ref = archive_evidence["ref"]
    license_spdx = archive_evidence["license_spdx"]
    if not all(isinstance(value, str) and value for value in (archive, repository, ref, license_spdx)):
        raise RepositoryRegistryError(f"promotion evidence string fields must be non-empty: {entry_id}")
    if repository.count("/") != 1:
        raise RepositoryRegistryError(f"promotion evidence repository must be exact owner/repo: {entry_id}")

    _validate_sha256(archive_evidence["archive_sha256"], "archive_sha256")
    _validate_sha(archive_evidence["commit_sha"], "commit_sha")
    _validate_sha(archive_evidence["tree_sha"], "tree_sha")

    if archive.casefold() != candidate["archive"].casefold():
        raise RepositoryRegistryError(f"promotion archive does not match candidate evidence: {entry_id}")
    if repository != candidate["candidate_repository"]:
        raise RepositoryRegistryError(f"promotion repository does not match candidate evidence: {entry_id}")
    candidate_license = candidate.get("candidate_license_spdx")
    if candidate_license is not None and candidate_license != license_spdx:
        raise RepositoryRegistryError(f"promotion license does not match candidate evidence: {entry_id}")

    entry = registry.by_id(entry_id)
    if entry["identity_status"] != "UNRESOLVED" or entry["decision"] != "PENDING":
        raise RepositoryRegistryError(f"promotion target is no longer unresolved/PENDING: {entry_id}")
    if archive.casefold() not in entry["source_locator"].casefold():
        raise RepositoryRegistryError(f"promotion archive does not match registry source: {entry_id}")

    decision = candidate["decision_if_matched"]
    if license_spdx.upper().startswith(_COPYLEFT_PREFIXES) and decision == "ADOPT":
        raise RepositoryRegistryError(f"copyleft archive cannot be proposed for ADOPT: {entry_id}")

    return {
        "registry_entry_id": entry_id,
        "archive": archive,
        "archive_sha256": archive_evidence["archive_sha256"],
        "canonical_repository": repository,
        "ref": ref,
        "commit_sha": archive_evidence["commit_sha"],
        "tree_sha": archive_evidence["tree_sha"],
        "license_spdx": license_spdx,
        "decision": decision,
        "archive_match": "EXACT_RECOMPUTED_GIT_TREE",
        "human_review_required": True,
        "registry_mutation_permitted": False,
    }


def load_candidate_evidence(
    registry: RepositoryRegistry,
    path: str | Path = DEFAULT_CANDIDATE_EVIDENCE_PATH,
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RepositoryRegistryError("candidate evidence is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RepositoryRegistryError("candidate evidence must be a JSON object")
    return validate_candidate_evidence(registry, payload)
