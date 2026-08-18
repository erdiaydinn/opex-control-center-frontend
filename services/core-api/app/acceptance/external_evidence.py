"""Master 49-55 fail-closed external acceptance evidence evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

EvidenceClass = Literal[
    "REPOSITORY",
    "SYNTHETIC",
    "MANAGED_STAGING",
    "REAL_STAGING",
    "REAL_ENVIRONMENT",
    "REAL_BUILD_UAT",
]
EvidenceStatus = Literal["MISSING", "PENDING", "PASS", "FAIL", "REVOKED"]

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EvidenceRecord:
    tenant_id: str
    release_id: str
    candidate_sha: str
    requirement_key: str
    evidence_key: str
    evidence_class: EvidenceClass
    status: EvidenceStatus
    environment: str
    provenance: str
    artifact_sha256: str
    approver: str
    observed_at: datetime
    expires_at: datetime


def load_requirements(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported acceptance schema")
    requirements = data.get("requirements", [])
    items = [int(item["item"]) for item in requirements]
    if items != list(range(49, 56)):
        raise ValueError("items 49-55 must be complete and ordered")
    return data


def _class_allowed(required: str, actual: EvidenceClass) -> bool:
    if actual in {"REPOSITORY", "SYNTHETIC"}:
        return False
    if required == "REAL_ENVIRONMENT":
        return actual == "REAL_ENVIRONMENT"
    if required == "REAL_STAGING":
        return actual in {"REAL_STAGING", "REAL_ENVIRONMENT"}
    if required == "REAL_BUILD_UAT":
        return actual in {"REAL_BUILD_UAT", "REAL_ENVIRONMENT"}
    if required == "MANAGED_STAGING_OR_REAL":
        return actual in {"MANAGED_STAGING", "REAL_STAGING", "REAL_ENVIRONMENT"}
    return False


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _validate_context(
    *,
    tenant_id: str,
    release_id: str,
    candidate_sha: str,
    as_of: datetime,
) -> None:
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not release_id.strip():
        raise ValueError("release_id is required")
    if not _SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be an exact lowercase 40-character commit SHA")
    if not _aware(as_of):
        raise ValueError("as_of must be timezone-aware")


def _evaluate_requirement(
    requirement: dict[str, object],
    records: tuple[EvidenceRecord, ...],
    *,
    tenant_id: str,
    release_id: str,
    candidate_sha: str,
    as_of: datetime,
) -> tuple[bool, tuple[str, ...], dict[str, EvidenceRecord]]:
    _validate_context(
        tenant_id=tenant_id,
        release_id=release_id,
        candidate_sha=candidate_sha,
        as_of=as_of,
    )
    expected = tuple(str(value) for value in requirement["evidence"])
    relevant = tuple(
        record
        for record in records
        if record.tenant_id == tenant_id
        and record.release_id == release_id
        and record.candidate_sha == candidate_sha
        and record.requirement_key == requirement["key"]
    )
    blockers: list[str] = []
    selected: dict[str, EvidenceRecord] = {}

    for key in expected:
        candidates = tuple(record for record in relevant if record.evidence_key == key)
        if not candidates:
            blockers.append(f"{key}:missing")
            continue
        invalid_window = any(
            not _aware(record.observed_at) or not _aware(record.expires_at)
            for record in candidates
        )
        if invalid_window:
            blockers.append(f"{key}:invalid_window")
            continue
        effective = tuple(record for record in candidates if record.observed_at <= as_of)
        if not effective:
            blockers.append(f"{key}:not_yet_effective")
            continue
        record = max(effective, key=lambda item: item.observed_at)
        selected[key] = record

        if record.status != "PASS":
            blockers.append(f"{key}:{record.status.lower()}")
            continue
        if record.expires_at <= record.observed_at or record.expires_at <= as_of:
            blockers.append(f"{key}:expired")
            continue
        if not _class_allowed(str(requirement["required_class"]), record.evidence_class):
            blockers.append(f"{key}:wrong_evidence_class")
            continue
        provenance_fields = (
            record.environment.strip(),
            record.provenance.strip(),
            record.approver.strip(),
        )
        if not all(provenance_fields):
            blockers.append(f"{key}:incomplete_provenance")
            continue
        if not _SHA64.fullmatch(record.artifact_sha256):
            blockers.append(f"{key}:invalid_artifact_digest")

    return not blockers, tuple(blockers), selected


def evaluate_requirement(
    requirement: dict[str, object],
    records: tuple[EvidenceRecord, ...],
    *,
    tenant_id: str,
    release_id: str,
    candidate_sha: str,
    as_of: datetime,
) -> tuple[bool, tuple[str, ...]]:
    ok, blockers, _ = _evaluate_requirement(
        requirement,
        records,
        tenant_id=tenant_id,
        release_id=release_id,
        candidate_sha=candidate_sha,
        as_of=as_of,
    )
    return ok, blockers


def evaluate_items_49_55(
    requirements: dict[str, object],
    records: tuple[EvidenceRecord, ...],
    *,
    tenant_id: str,
    release_id: str,
    candidate_sha: str,
    as_of: datetime,
) -> dict[int, bool]:
    return {
        int(requirement["item"]): evaluate_requirement(
            requirement,
            records,
            tenant_id=tenant_id,
            release_id=release_id,
            candidate_sha=candidate_sha,
            as_of=as_of,
        )[0]
        for requirement in requirements["requirements"]
    }


def build_external_item_refs(
    requirements: dict[str, object],
    records: tuple[EvidenceRecord, ...],
    *,
    tenant_id: str,
    release_id: str,
    candidate_sha: str,
    as_of: datetime,
) -> dict[int, str]:
    """Return deterministic ledger fingerprints only for currently passing items."""

    refs: dict[int, str] = {}
    for requirement in requirements["requirements"]:
        ok, _, selected = _evaluate_requirement(
            requirement,
            records,
            tenant_id=tenant_id,
            release_id=release_id,
            candidate_sha=candidate_sha,
            as_of=as_of,
        )
        if not ok:
            continue
        parts = [tenant_id, release_id, candidate_sha, str(requirement["key"])]
        parts.extend(
            f"{key}:{selected[key].artifact_sha256}:{selected[key].observed_at.isoformat()}"
            for key in sorted(selected)
        )
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        refs[int(requirement["item"])] = f"ledger-sha256:{digest}"
    return refs
