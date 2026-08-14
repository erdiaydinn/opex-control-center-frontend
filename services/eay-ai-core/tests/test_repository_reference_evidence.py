from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.repository_reference_evidence import load_repository_reference_evidence_text

CONFIG_DIR = Path(__file__).parents[1] / "config"
QDRANT_EVIDENCE_PATH = CONFIG_DIR / "repository_reference_evidence_qdrant.json"
PROMPTFOO_EVIDENCE_PATH = CONFIG_DIR / "repository_reference_evidence_promptfoo.json"


def _payload(path: Path = QDRANT_EVIDENCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_qdrant_reference_evidence_is_valid_and_non_authoritative() -> None:
    evidence = load_repository_reference_evidence_text(QDRANT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence.repository == "qdrant/qdrant"
    assert evidence.commit_sha == "74f3e85b9473c62560006c043e13737ce6b48412"
    assert evidence.tree_sha == "522b0ad27ad981c7e776e3cbe32fef2e50b92978"
    assert evidence.license.spdx == "Apache-2.0"
    assert evidence.authority == "REFERENCE_ONLY"
    assert evidence.provenance.registry_promotion == "PENDING_CANONICAL_REGISTRY_REVIEW"


def test_promptfoo_reference_evidence_pins_eval_execution_trust_boundary() -> None:
    evidence = load_repository_reference_evidence_text(PROMPTFOO_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence.repository == "promptfoo/promptfoo"
    assert evidence.commit_sha == "af026d02115c31dad4bebe0484ab5b6a3a62f6e2"
    assert evidence.tree_sha == "ddccaa1ee49edda851791d4f3dc0c5ce6f70c7a3"
    assert evidence.license.spdx == "MIT"
    assert evidence.authority == "REFERENCE_ONLY"
    security = evidence.security_relevance.casefold()
    assert "without a sandbox" in security
    assert "isolated" in security
    assert "scoped credentials" in security
    assert "restricted egress" in security
    assert "not an execution sandbox" in security


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


def test_promptfoo_reference_evidence_cannot_be_escalated_to_adopt() -> None:
    payload = _payload(PROMPTFOO_EVIDENCE_PATH)
    payload["decision"] = "ADOPT"
    with pytest.raises(ValidationError):
        load_repository_reference_evidence_text(json.dumps(payload))
