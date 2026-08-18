import json
from pathlib import Path

import pytest

from app.ai_core.substrate_contract import (
    FROZEN_AI_CORE_HEAD,
    authorize_consumer,
    load_substrate_contract,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "docs/governance/eay_ai_core_shared_substrate.json"


def test_frozen_ai_core_is_shared_without_mutating_pr15() -> None:
    contract = load_substrate_contract(CONTRACT_PATH)
    assert contract.frozen_pr == 15
    assert contract.frozen_head_sha == FROZEN_AI_CORE_HEAD
    assert {
        "grounded_rag",
        "model_registry",
        "canary",
        "vision_provenance",
        "promotion_gate",
    } <= contract.capabilities
    assert {"jarvis", "budget", "academy", "planogram"} <= contract.consumers


def test_consumer_requires_tenant_and_provenance() -> None:
    contract = load_substrate_contract(CONTRACT_PATH)
    assert authorize_consumer(
        contract,
        module="jarvis",
        tenant_authorized=True,
        provenance_bound=True,
    )
    assert not authorize_consumer(
        contract,
        module="jarvis",
        tenant_authorized=False,
        provenance_bound=True,
    )
    assert not authorize_consumer(
        contract,
        module="unknown",
        tenant_authorized=True,
        provenance_bound=True,
    )


def test_frozen_head_and_truth_boundaries_fail_closed(tmp_path: Path) -> None:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["frozen_baseline"]["head_sha"] = "0" * 40
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen PR #15"):
        load_substrate_contract(mutated)

    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["truth_boundaries"]["synthetic_is_production_evidence"] = True
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="production truth boundary"):
        load_substrate_contract(mutated)
