from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.repository_reference_evidence import load_repository_reference_evidence_text

EVIDENCE_PATH = Path(__file__).parents[1] / "config" / "repository_reference_evidence_qdrant.json"


def _payload() -> dict:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_qdrant_reference_evidence_is_valid_and_non_authoritative() -> None:
    evidence = load_repository_reference_evidence_text(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence.repository == "qdrant/qdrant"
    assert evidence.commit_sha == "74f3e85b9473c62560006c043e13737ce6b48412"
    assert evidence.tree_sha == "522b0ad27ad981c7e776e3cbe32fef2e50b92978"
    assert evidence.license.spdx == "Apache-2.0"
    assert evidence.authority == "REFERENCE_ONLY"
    assert evidence.provenance.registry_promotion == "PENDING_CANONICAL_REGISTRY_REVIEW"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority", "ADOPT"),
        ("decision", "ADOPT"),
        ("commit_sha", "0" * 39),
        ("tree_sha", "not-a-git-tree"),
        ("canonical_upstream", "attacker/qdrant"),
    ],
)
def test_reference_evidence_rejects_authority_or_identity_substitution(field: str, value: str) -> None:
    payload = _payload()
    payload[field] = value
    with pytest.raises((ValidationError, ValueError)):
        load_repository_reference_evidence_text(json.dumps(payload))


def test_reference_evidence_cannot_claim_supplied_archive_match() -> None:
    payload = _payload()
    payload["provenance"]["supplied_archive_match"] = "EXACT_RECOMPUTED_GIT_TREE"
    with pytest.raises(ValidationError):
        load_repository_reference_evidence_text(json.dumps(payload))


def test_reference_evidence_cannot_claim_registry_promotion() -> None:
    payload = _payload()
    payload["provenance"]["registry_promotion"] = "VERIFIED"
    with pytest.raises(ValidationError):
        load_repository_reference_evidence_text(json.dumps(payload))
