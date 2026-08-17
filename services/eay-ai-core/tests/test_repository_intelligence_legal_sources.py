import json

from app.repository_intelligence import load_repository_registry, load_repository_registry_text


def test_turkish_legal_sources_are_versioned_first_class_registry_entries():
    registry = load_repository_registry()
    entries = registry.by_id()

    assert registry.version >= 2

    yargi = entries["yargi-mcp"]
    assert yargi.classification == "DISCOVERED"
    assert yargi.identity == "saidsurucu/yargi-mcp"
    assert yargi.decision == "adopt"
    assert yargi.review.commit == "2ead0b455c83c79275f704af7f92ff3392876e71"
    assert yargi.review.license == "MIT"

    legal_tr = entries["claude-legal-turkish"]
    assert legal_tr.classification == "DISCOVERED"
    assert legal_tr.identity == "ZekaiSuni/claude-for-legal-turkish"
    assert legal_tr.decision == "reference"
    assert legal_tr.review.commit == "6ede1c82f3aa6bb36216a961f4ec32c6b9b14362"
    assert legal_tr.review.license == "Apache-2.0"


def test_historical_v1_registry_remains_loadable_without_new_v2_seeds():
    payload = load_repository_registry().model_dump(mode="json")
    payload["version"] = 1
    payload["repositories"] = [
        entry
        for entry in payload["repositories"]
        if entry["id"] not in {"yargi-mcp", "claude-legal-turkish"}
    ]

    historical = load_repository_registry_text(json.dumps(payload))

    assert historical.version == 1
    assert "yargi-mcp" not in historical.by_id()
    assert "claude-legal-turkish" not in historical.by_id()
