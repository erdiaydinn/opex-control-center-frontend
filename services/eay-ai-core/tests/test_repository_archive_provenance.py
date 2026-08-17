from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.repository_archive_provenance import (
    load_archive_provenance,
    load_archive_provenance_text,
    validate_archive_provenance_against_registry,
    verified_archive_registry_ids,
)
from app.repository_intelligence import load_repository_registry_text

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "config" / "repository_intelligence_registry.json"
PROVENANCE_PATH = ROOT / "config" / "repository_archive_provenance.json"


def _registry_payload() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _ledger_payload() -> dict[str, object]:
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


def test_canonical_archive_ledger_matches_registry() -> None:
    registry = load_repository_registry_text(REGISTRY_PATH.read_text(encoding="utf-8"))
    ledger = load_archive_provenance(PROVENANCE_PATH)

    assert verified_archive_registry_ids(registry, ledger) == (
        "imported-cl4r1t4s",
        "imported-council-of-high-intelligence",
        "imported-computer-lab-automation",
    )
    assert len(ledger.fingerprint()) == 64


def test_verified_supplied_archive_cannot_silently_lose_evidence() -> None:
    payload = _ledger_payload()
    payload["records"] = [
        record
        for record in payload["records"]
        if record["registry_entry_id"] != "imported-council-of-high-intelligence"
    ]
    registry = load_repository_registry_text(REGISTRY_PATH.read_text(encoding="utf-8"))
    ledger = load_archive_provenance_text(json.dumps(payload))

    with pytest.raises(ValueError, match="verified_registry_entries_missing"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_unresolved_candidate_cannot_be_promoted_by_ledger() -> None:
    registry_payload = _registry_payload()
    ledger_payload = _ledger_payload()
    source = next(
        record
        for record in ledger_payload["records"]
        if record["registry_entry_id"] == "imported-council-of-high-intelligence"
    )
    forged = dict(source)
    forged.update(
        {
            "registry_entry_id": "imported-deep-learning-tutorials",
            "archive": "Deep-Learning-Tutorials-master.zip",
            "canonical_repository": "lisa-lab/DeepLearningTutorials",
            "ref": "master",
            "commit_sha": "11c465105026cf87573937fc2d35ab7543678698",
            "tree_sha": "b81e33450a82945b26ff6c3a93144667f8327ba6",
            "license": {"spdx": "BSD-3-Clause", "status": "VERIFIED"},
            "decision": "REFERENCE",
        }
    )
    ledger_payload["records"].append(forged)
    registry = load_repository_registry_text(json.dumps(registry_payload))
    ledger = load_archive_provenance_text(json.dumps(ledger_payload))

    with pytest.raises(ValueError, match="cannot_promote_unresolved_entry"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_repository_substitution_fails_closed() -> None:
    registry = load_repository_registry_text(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload = _ledger_payload()
    payload["records"][0]["canonical_repository"] = "attacker/CL4R1T4S"
    ledger = load_archive_provenance_text(json.dumps(payload))

    with pytest.raises(ValueError, match="repository_mismatch"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_commit_substitution_fails_closed() -> None:
    registry = load_repository_registry_text(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload = _ledger_payload()
    payload["records"][1]["commit_sha"] = "0" * 40
    ledger = load_archive_provenance_text(json.dumps(payload))

    with pytest.raises(ValueError, match="review_commit_mismatch"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_license_substitution_fails_closed() -> None:
    registry = load_repository_registry_text(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload = _ledger_payload()
    payload["records"][2]["license"] = {"spdx": "MIT", "status": "VERIFIED"}
    ledger = load_archive_provenance_text(json.dumps(payload))

    with pytest.raises(ValueError, match="license_mismatch"):
        validate_archive_provenance_against_registry(registry, ledger)


def test_invalid_archive_digest_is_rejected_before_registry_validation() -> None:
    payload = _ledger_payload()
    payload["records"][0]["archive_sha256"] = "not-a-digest"

    with pytest.raises(ValidationError):
        load_archive_provenance_text(json.dumps(payload))


def test_copyleft_record_cannot_claim_adopt() -> None:
    payload = _ledger_payload()
    payload["records"][0]["decision"] = "ADOPT"

    with pytest.raises(ValidationError, match="copyleft_archive_cannot_be_adoption_authority"):
        load_archive_provenance_text(json.dumps(payload))
