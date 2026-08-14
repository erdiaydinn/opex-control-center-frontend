from __future__ import annotations

import json
from pathlib import Path

from app.repository_intelligence import load_repository_registry


ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "config" / "repository_intelligence_registry.json"
PROVENANCE_PATH = ROOT / "config" / "repository_archive_provenance.json"


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def test_exact_archive_matches_are_promoted_without_weakening_license_policy() -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))

    assert provenance["schema_version"] == 1
    assert provenance["records"]

    for record in provenance["records"]:
        assert record["match"] == "EXACT_RECOMPUTED_GIT_TREE"
        assert _is_hex(record["archive_sha256"], 64)
        assert _is_hex(record["commit_sha"], 40)
        assert _is_hex(record["tree_sha"], 40)
        assert _is_hex(record["readme_blob_sha"], 40)
        assert _is_hex(record["license_blob_sha"], 40)

        entry = registry.by_id(record["registry_entry_id"])
        assert entry["classification"] == "IMPORTED"
        assert entry["identity_status"] == "VERIFIED"
        assert entry["repository"] == record["canonical_repository"]
        assert entry["canonical_upstream"] == record["canonical_repository"]
        assert entry["source_locator"] == record["archive"]
        assert entry["license"] == record["license"]

        if record["commercial_use"].startswith("REFERENCE_ONLY"):
            assert entry["decision"] == "REFERENCE"
        assert entry["decision"] != "ADOPT"


def test_copyleft_archive_matches_remain_reference_only() -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))

    by_id = {record["registry_entry_id"]: record for record in provenance["records"]}
    for entry_id, expected_spdx in (
        ("imported-cl4r1t4s", "AGPL-3.0"),
        ("imported-computer-lab-automation", "GPL-3.0"),
    ):
        record = by_id[entry_id]
        entry = registry.by_id(entry_id)
        assert record["license"] == {"spdx": expected_spdx, "status": "VERIFIED"}
        assert entry["license"] == record["license"]
        assert entry["decision"] == "REFERENCE"
        assert "REFERENCE_ONLY" in record["commercial_use"]
