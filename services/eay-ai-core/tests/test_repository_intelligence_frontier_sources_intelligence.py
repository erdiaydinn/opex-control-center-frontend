import json
from pathlib import Path

from app.repository_intelligence import RepositoryEntry

SUPPLEMENT = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "repository_intelligence_registry_supplement_v5.json"
)


def _entries() -> dict[str, RepositoryEntry]:
    payload = json.loads(SUPPLEMENT.read_text(encoding="utf-8"))
    return {
        item["id"]: RepositoryEntry.model_validate(item)
        for item in payload["repositories"]
    }


def test_frontier_jarvis_references_are_pinned_and_preserved() -> None:
    entries = _entries()
    required = {
        "sherpa-onnx",
        "samuel-screen-voice-agent",
        "agentoperations-agent-registry",
        "robotmcp-ros-mcp-server",
    }
    assert required.issubset(entries)
    for source_id in required:
        assert entries[source_id].review.commit is not None
        assert len(entries[source_id].review.commit or "") == 40


def test_unverified_agent_registry_license_is_reference_only_and_blocked() -> None:
    entry = _entries()["agentoperations-agent-registry"]
    assert entry.decision == "reference"
    assert entry.review.license == "pending-review"
    assert entry.review.commercial_use.startswith("blocked")


def test_robotics_reference_does_not_claim_production_adoption() -> None:
    entry = _entries()["robotmcp-ros-mcp-server"]
    assert entry.decision == "reference"
    assert "physical-ai-integration-reference" in entry.capabilities
    assert "until-physical-safety-acceptance" in entry.review.commercial_use
