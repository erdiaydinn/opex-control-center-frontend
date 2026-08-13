from __future__ import annotations

import json
from pathlib import Path


CONFIG_ROOT = Path(__file__).parents[1] / "config"
REGISTRY_PATH = CONFIG_ROOT / "repository_intelligence_registry.json"
CANDIDATE_PATH = CONFIG_ROOT / "repository_intelligence_candidate_evidence.json"


def test_candidate_evidence_never_promotes_unresolved_registry_entries() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    evidence = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    entries = {item["id"]: item for item in registry["entries"]}

    assert evidence["schema_version"] == 1
    assert evidence["candidates"]

    for candidate in evidence["candidates"]:
        entry = entries[candidate["registry_entry_id"]]
        assert entry["identity_status"] == "UNRESOLVED"
        assert entry["repository"] is None
        assert entry["canonical_upstream"] is None
        assert entry["decision"] == "PENDING"
        assert entry["license"] == {"spdx": None, "status": "PENDING"}
        assert candidate["promotion_status"].startswith("BLOCKED_")


def test_candidate_sha_fields_are_exact_when_present() -> None:
    evidence = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))

    for candidate in evidence["candidates"]:
        for field in ("candidate_head_sha", "candidate_tree_sha"):
            value = candidate[field]
            if value is not None:
                assert len(value) == 40
                assert set(value) <= set("0123456789abcdef")


def test_no_archive_is_marked_verified_without_archive_side_match() -> None:
    evidence = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))

    for candidate in evidence["candidates"]:
        assert candidate["archive_match_status"] != "VERIFIED"
