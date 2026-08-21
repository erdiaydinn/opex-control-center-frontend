from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_canonical_lineage.py"
SPEC = importlib.util.spec_from_file_location("eay_validate_canonical_lineage", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_repository_manifest_and_release_truth_are_valid() -> None:
    manifest = MODULE.validate_manifest(ROOT)
    assert manifest["canonical_continuation"]["pr"] == 94
    assert manifest["canonical_continuation"]["main_merge_permitted"] is False
    assert manifest["pr_roles"]["frozen"] == [15, 16]


def test_open_pr_inventory_count_matches_every_classified_role() -> None:
    manifest = MODULE.validate_manifest(ROOT)
    classified = sum(len(items) for items in manifest["pr_roles"].values())
    assert manifest["open_pr_inventory"]["observed_count"] == classified == 62


def test_open_pr_inventory_count_drift_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    manifest = json.loads((ROOT / "config/eay_canonical_lineage.json").read_text(encoding="utf-8"))
    release = json.loads((ROOT / "config/eay_release_candidate.json").read_text(encoding="utf-8"))
    manifest["open_pr_inventory"]["observed_count"] = 61
    (tmp_path / "config/eay_canonical_lineage.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "config/eay_release_candidate.json").write_text(json.dumps(release), encoding="utf-8")

    with pytest.raises(MODULE.LineageValidationError, match="open PR inventory count mismatch"):
        MODULE.validate_manifest(tmp_path)


def test_frozen_ai_core_is_pinned_without_false_direct_ancestry_claim() -> None:
    manifest = MODULE.validate_manifest(ROOT)
    anchors = {anchor["pr"]: anchor for anchor in manifest["immutable_anchors"]}
    assert anchors[15]["head_sha"] == "9e1422df2a584b71593c2f6188d26c8ab4ab4c15"
    assert anchors[15]["remote_tip_must_equal"] is True
    assert anchors[15]["must_be_ancestor_of_category_head"] is False


def test_security_and_release_anchors_remain_required_category_ancestors() -> None:
    manifest = MODULE.validate_manifest(ROOT)
    anchors = {anchor["pr"]: anchor for anchor in manifest["immutable_anchors"]}
    assert anchors[16]["must_be_ancestor_of_category_head"] is True
    assert anchors[76]["must_be_ancestor_of_category_head"] is True


def test_release_policy_cannot_silently_claim_production_ready(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    manifest = json.loads((ROOT / "config/eay_canonical_lineage.json").read_text(encoding="utf-8"))
    release = json.loads((ROOT / "config/eay_release_candidate.json").read_text(encoding="utf-8"))
    release["release_controls"]["production_ready"] = True
    (tmp_path / "config/eay_canonical_lineage.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "config/eay_release_candidate.json").write_text(json.dumps(release), encoding="utf-8")

    with pytest.raises(MODULE.LineageValidationError, match="production_ready must remain false"):
        MODULE.validate_manifest(tmp_path)


def test_category_pull_request_shape_rejects_main_and_wrong_branch() -> None:
    manifest = MODULE.validate_manifest(ROOT)
    with pytest.raises(MODULE.LineageValidationError, match="must never target main"):
        MODULE.validate_pull_request_shape(
            manifest,
            {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_BASE_REF": "main",
                "GITHUB_HEAD_REF": "product/eay-category-leadership-v1",
            },
        )

    with pytest.raises(MODULE.LineageValidationError, match="unexpected PR head"):
        MODULE.validate_pull_request_shape(
            manifest,
            {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_BASE_REF": "product/eay-product-completion-v1",
                "GITHUB_HEAD_REF": "some-other-branch",
            },
        )
