from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.repository_reference_evidence import load_repository_reference_evidence_text

CONFIG_DIR = Path(__file__).parents[1] / "config"
QDRANT_EVIDENCE_PATH = CONFIG_DIR / "repository_reference_evidence_qdrant.json"
PROMPTFOO_EVIDENCE_PATH = CONFIG_DIR / "repository_reference_evidence_promptfoo.json"
PHOENIX_EVIDENCE_PATH = CONFIG_DIR / "repository_reference_evidence_phoenix.json"
MLFLOW_EVIDENCE_PATH = CONFIG_DIR / "repository_reference_evidence_mlflow.json"


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


def test_phoenix_reference_evidence_preserves_elastic_2_hosting_boundary() -> None:
    evidence = load_repository_reference_evidence_text(PHOENIX_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence.repository == "Arize-ai/phoenix"
    assert evidence.commit_sha == "4090acd0d248e1ed03d37bf339c9975ee171c7ff"
    assert evidence.tree_sha == "9b64d0f178bf2721a62e914a1a7a38553e0cbf6f"
    assert evidence.license.spdx == "Elastic-2.0"
    assert evidence.commercial_use == "SOURCE_AVAILABLE_NO_HOSTED_MANAGED_SERVICE"
    security = evidence.security_relevance.casefold()
    assert "hosted" in security
    assert "managed service" in security
    assert evidence.authority == "REFERENCE_ONLY"


def test_mlflow_reference_evidence_pins_model_weight_promotion_boundary() -> None:
    evidence = load_repository_reference_evidence_text(MLFLOW_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence.repository == "mlflow/mlflow"
    assert evidence.commit_sha == "3b1b40722bde72efd8cb0b91b97e2c2d2c50d0ac"
    assert evidence.tree_sha == "e263a3493a1d79cc816ec5087e18ac0c8340748b"
    assert evidence.license.spdx == "Apache-2.0"
    assert "model-registry" in evidence.capabilities
    security = evidence.security_relevance.casefold()
    assert "human approval" in security
    assert "production model-weight" in security
    assert "artifact provenance" in security
    assert "deployment authorization" in security
    assert evidence.authority == "REFERENCE_ONLY"


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


def test_phoenix_elastic_2_reference_cannot_be_relabelled_permissive() -> None:
    payload = _payload(PHOENIX_EVIDENCE_PATH)
    payload["commercial_use"] = "PERMISSIVE_WITH_NOTICE"
    with pytest.raises(ValidationError, match="hosted_service_restriction"):
        load_repository_reference_evidence_text(json.dumps(payload))


def test_phoenix_elastic_2_reference_requires_visible_hosting_boundary() -> None:
    payload = _payload(PHOENIX_EVIDENCE_PATH)
    payload["security_relevance"] = "Observability reference only."
    with pytest.raises(ValidationError, match="security_license_boundary"):
        load_repository_reference_evidence_text(json.dumps(payload))


def test_mlflow_model_lifecycle_reference_cannot_drop_human_approval_boundary() -> None:
    payload = _payload(MLFLOW_EVIDENCE_PATH)
    payload["security_relevance"] = (
        "MLflow is a model-lifecycle reference with production model-weight controls, "
        "tenant-scoped artifact provenance, and deployment authorization."
    )
    with pytest.raises(ValidationError, match="model_lifecycle_reference_requires_production_promotion_boundary"):
        load_repository_reference_evidence_text(json.dumps(payload))


def test_mlflow_model_lifecycle_reference_cannot_drop_deployment_authorization_boundary() -> None:
    payload = _payload(MLFLOW_EVIDENCE_PATH)
    payload["security_relevance"] = (
        "MLflow is a model-lifecycle reference with human approval, production model-weight controls, "
        "and tenant-scoped artifact provenance."
    )
    with pytest.raises(ValidationError, match="model_lifecycle_reference_requires_production_promotion_boundary"):
        load_repository_reference_evidence_text(json.dumps(payload))
