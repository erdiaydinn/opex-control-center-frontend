"""Master 49-55 fail-closed external acceptance evidence evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
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
EvidenceStatus = Literal["MISSING", "PENDING", "PASS", "FAIL"]


@dataclass(frozen=True)
class EvidenceRecord:
    requirement_key: str
    evidence_key: str
    evidence_class: EvidenceClass
    status: EvidenceStatus
    environment: str
    provenance: str
    approver: str


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


def evaluate_requirement(
    requirement: dict[str, object],
    records: tuple[EvidenceRecord, ...],
) -> tuple[bool, tuple[str, ...]]:
    expected = tuple(str(value) for value in requirement["evidence"])
    matching = {
        record.evidence_key: record
        for record in records
        if record.requirement_key == requirement["key"]
    }
    blockers: list[str] = []

    for key in expected:
        record = matching.get(key)
        if record is None:
            blockers.append(f"{key}:missing")
            continue
        if record.status != "PASS":
            blockers.append(f"{key}:{record.status.lower()}")
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

    return not blockers, tuple(blockers)


def evaluate_items_49_55(
    requirements: dict[str, object],
    records: tuple[EvidenceRecord, ...],
) -> dict[int, bool]:
    return {
        int(requirement["item"]): evaluate_requirement(requirement, records)[0]
        for requirement in requirements["requirements"]
    }
