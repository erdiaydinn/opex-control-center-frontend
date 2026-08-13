from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_archive_provenance import (
    DEFAULT_ARCHIVE_PROVENANCE_PATH,
    ArchiveProvenanceLedger,
    load_archive_provenance,
    load_archive_provenance_text,
    validate_archive_provenance_against_registry,
    verified_archive_registry_ids,
)
from app.repository_intelligence import load_repository_registry


def test_versioned_archive_provenance_matches_canonical_registry():
    registry = load_repository_registry()
    ledger = load_archive_provenance()

    validate_archive_provenance_against_registry(registry, ledger)
    assert verified_archive_registry_ids(registry, ledger) == (
        "cl4r1t4s",
        "council-high-intelligence",
        "computer-lab-automation",
    )
    assert len(ledger.fingerprint()) == 64


def test_copyleft_archive_evidence_is_reference_only():
    ledger = load_archive_provenance()
    records = ledger.by_registry_entry_id()

    assert records["cl4r1t4s"].license.spdx == "AGPL-3.0"
    assert records["cl4r1t4s"].decision == "REFERENCE"
    assert records["computer-lab-automation"].license.spdx == "GPL-3.0"
    assert records["computer-lab-automation"].decision == "REFERENCE"


def test_archive_provenance_rejects_repository_substitution():
    registry = load_repository_registry()
    payload = json.loads(DEFAULT_ARCHIVE_PROVENANCE_PATH.read_text(encoding="utf-8"))
    payload["records"][0]["canonical_repository"] = "attacker/CL4R1T4S"
    ledger = load_archive_provenance_text(json.dumps(payload))

    with pytest.raises(ValueError, match="archive_provenance_repository_mismatch:cl4r1t4s"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_archive_provenance_rejects_commit_substitution():
    registry = load_repository_registry()
    payload = json.loads(DEFAULT_ARCHIVE_PROVENANCE_PATH.read_text(encoding="utf-8"))
    payload["records"][1]["commit_sha"] = "a" * 40
    ledger = load_archive_provenance_text(json.dumps(payload))

    with pytest.raises(ValueError, match="archive_provenance_review_revision_mismatch:council-high-intelligence"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_archive_provenance_rejects_source_artifact_mismatch():
    registry_payload = load_repository_registry().model_dump(mode="json")
    for entry in registry_payload["repositories"]:
        if entry["id"] == "computer-lab-automation":
            entry["source_artifact"] = "different.zip"
            break
    registry = type(load_repository_registry()).model_validate(registry_payload)
    ledger = load_archive_provenance()

    with pytest.raises(ValueError, match="archive_provenance_source_artifact_mismatch:computer-lab-automation"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_archive_provenance_rejects_commercial_use_widening():
    registry_payload = load_repository_registry().model_dump(mode="json")
    for entry in registry_payload["repositories"]:
        if entry["id"] == "cl4r1t4s":
            entry["review"]["commercial_use"] = "allowed"
            break
    registry = type(load_repository_registry()).model_validate(registry_payload)
    ledger = load_archive_provenance()

    with pytest.raises(ValueError, match="archive_provenance_commercial_use_mismatch:cl4r1t4s"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_archive_ledger_rejects_duplicate_registry_identity():
    payload = json.loads(DEFAULT_ARCHIVE_PROVENANCE_PATH.read_text(encoding="utf-8"))
    payload["records"].append(dict(payload["records"][0]))

    with pytest.raises(ValueError, match="duplicate_archive_registry_entry_id"):
        ArchiveProvenanceLedger.model_validate(payload)


def test_archive_ledger_rejects_copyleft_adoption_authority():
    payload = json.loads(DEFAULT_ARCHIVE_PROVENANCE_PATH.read_text(encoding="utf-8"))
    payload["records"][0]["decision"] = "ADOPT"

    with pytest.raises(ValueError, match="copyleft_archive_cannot_be_adoption_authority"):
        ArchiveProvenanceLedger.model_validate(payload)


def test_archive_provenance_json_is_repo_relative_and_contains_no_raw_archive_bytes():
    path = Path(DEFAULT_ARCHIVE_PROVENANCE_PATH)
    text = path.read_text(encoding="utf-8")

    assert path.name == "repository_archive_provenance.json"
    assert "archive_sha256" in text
    assert "PK\\x03\\x04" not in text
