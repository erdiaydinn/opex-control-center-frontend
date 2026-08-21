#!/usr/bin/env python3
"""Fail-closed validator for the EAY canonical continuation.

Repository-only validation checks the version-controlled lineage manifest and release
truth boundary. Full validation additionally resolves remote branch tips and proves
that the rolling product-completion line and immutable release/security anchors are
contained in the active category-leadership continuation.

The frozen AI Core PR #15 is deliberately pinned by exact remote tip only. Its work
was composed into later convergence history and is not required to be a direct Git
ancestor of the cumulative platform branch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

SHA40 = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_PATH = Path("config/eay_canonical_lineage.json")


class LineageValidationError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LineageValidationError(f"cannot load JSON contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LineageValidationError(f"JSON contract must be an object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LineageValidationError(message)


def _validate_unique(values: list[Any], label: str) -> None:
    _require(len(values) == len(set(values)), f"duplicate {label} entries are forbidden")


def validate_manifest(repo_root: Path) -> dict[str, Any]:
    manifest_path = repo_root / MANIFEST_PATH
    manifest = _load_json(manifest_path)
    _require(manifest.get("schema_version") == 1, "unsupported canonical-lineage schema")

    continuation = manifest.get("canonical_continuation")
    _require(isinstance(continuation, dict), "canonical_continuation is required")
    _require(continuation.get("pr") == 94, "PR #94 must remain the active category continuation")
    _require(
        continuation.get("head_branch") == "product/eay-category-leadership-v1",
        "unexpected category-leadership branch",
    )
    _require(
        continuation.get("base_branch") == "product/eay-product-completion-v1",
        "unexpected rolling product-completion base branch",
    )
    _require(continuation.get("base_must_be_ancestor_of_head") is True, "rolling base ancestry gate must stay enabled")
    for control in ("main_merge_permitted", "force_push_permitted", "production_activation_permitted"):
        _require(continuation.get(control) is False, f"{control} must remain false")

    rolling = manifest.get("rolling_parent")
    _require(isinstance(rolling, dict), "rolling_parent is required")
    _require(rolling.get("pr") == 92, "PR #92 must remain the rolling product-completion parent")
    _require(rolling.get("branch") == continuation.get("base_branch"), "rolling parent/base branch mismatch")
    _require(
        rolling.get("release_parent_branch") == "release/platform-convergence-v0.1",
        "unexpected release parent branch",
    )

    anchors = manifest.get("immutable_anchors")
    _require(isinstance(anchors, list) and anchors, "immutable_anchors must be non-empty")
    names: list[str] = []
    prs: list[int] = []
    branches: list[str] = []
    for raw in anchors:
        _require(isinstance(raw, dict), "each immutable anchor must be an object")
        name = raw.get("name")
        pr = raw.get("pr")
        branch = raw.get("branch")
        sha = raw.get("head_sha")
        _require(isinstance(name, str) and name.strip(), "anchor name is required")
        _require(isinstance(pr, int) and pr > 0, f"invalid PR number for anchor {name}")
        _require(isinstance(branch, str) and branch.strip(), f"invalid branch for anchor {name}")
        _require(isinstance(sha, str) and SHA40.fullmatch(sha) is not None, f"invalid SHA for anchor {name}")
        _require(raw.get("remote_tip_must_equal") is True, f"anchor {name} must pin its remote tip")
        names.append(name)
        prs.append(pr)
        branches.append(branch)
    _validate_unique(names, "anchor name")
    _validate_unique(prs, "anchor PR")
    _validate_unique(branches, "anchor branch")

    anchor_by_pr = {raw["pr"]: raw for raw in anchors}
    _require(anchor_by_pr.get(15, {}).get("must_be_ancestor_of_category_head") is False, "frozen AI Core #15 must not be given false direct-ancestry semantics")
    _require(anchor_by_pr.get(16, {}).get("must_be_ancestor_of_category_head") is True, "frozen Security #16 must remain a category ancestor")
    _require(anchor_by_pr.get(76, {}).get("must_be_ancestor_of_category_head") is True, "RC0 #76 must remain a category ancestor")

    roles = manifest.get("pr_roles")
    _require(isinstance(roles, dict), "pr_roles is required")
    all_role_prs: list[int] = []
    for role, raw_prs in roles.items():
        _require(isinstance(raw_prs, list) and all(isinstance(item, int) for item in raw_prs), f"invalid PR role list: {role}")
        _validate_unique(raw_prs, f"PR in role {role}")
        all_role_prs.extend(raw_prs)
    _validate_unique(all_role_prs, "PR role assignment")
    _require(roles.get("frozen") == [15, 16], "frozen PR role must remain exactly #15/#16")
    _require(94 in roles.get("active_category_leadership", []), "PR #94 must be active category authority")
    _require(92 in roles.get("rolling_product_completion", []), "PR #92 must be rolling product-completion authority")
    _require(76 in roles.get("release_anchor", []), "PR #76 must remain release anchor")

    inventory = manifest.get("open_pr_inventory")
    _require(isinstance(inventory, dict), "open_pr_inventory is required")
    observed_count = inventory.get("observed_count")
    _require(isinstance(observed_count, int) and observed_count > 0, "open PR observed_count must be positive")
    _require(
        observed_count == len(all_role_prs),
        f"open PR inventory count mismatch: observed={observed_count}, classified={len(all_role_prs)}",
    )
    for key in ("authority_rule", "closure_policy"):
        value = inventory.get(key)
        _require(isinstance(value, str) and value.strip(), f"open PR inventory {key} is required")

    truth = manifest.get("production_truth")
    _require(isinstance(truth, dict), "production_truth contract is required")
    release_policy_path = truth.get("release_policy_path")
    _require(isinstance(release_policy_path, str) and release_policy_path, "release policy path is required")
    release_policy = _load_json(repo_root / release_policy_path)
    controls = release_policy.get("release_controls")
    evidence = release_policy.get("evidence_policy")
    _require(isinstance(controls, dict), "release_controls missing")
    _require(isinstance(evidence, dict), "evidence_policy missing")

    for key in truth.get("required_false_controls", []):
        _require(controls.get(key) is False, f"release control {key} must remain false")
    for key in truth.get("required_true_evidence_rules", []):
        _require(evidence.get(key) is True, f"release evidence rule {key} must remain true")
    _require(controls.get("frozen_security_and_ai_foundations_may_not_be_mutated_for_rc") is True, "frozen foundation release control must remain enabled")
    _require(evidence.get("all_required_ci_must_pass_on_exact_head") is True, "exact-head CI rule must remain enabled")
    _require(evidence.get("runtime_github_sha_is_authoritative") is True, "runtime GitHub SHA must remain authoritative")

    return manifest


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise LineageValidationError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout.strip()


def _fetch_remote_branch(repo_root: Path, branch: str) -> str:
    remote_ref = f"refs/remotes/origin/{branch}"
    _git(repo_root, "fetch", "--no-tags", "origin", f"+refs/heads/{branch}:{remote_ref}")
    sha = _git(repo_root, "rev-parse", "--verify", remote_ref)
    _require(SHA40.fullmatch(sha) is not None, f"remote branch {branch} did not resolve to a commit SHA")
    return sha


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise LineageValidationError(
        f"git ancestry check failed for {ancestor} -> {descendant}: {result.stderr.strip()}"
    )


def validate_pull_request_shape(manifest: Mapping[str, Any], env: Mapping[str, str]) -> None:
    if env.get("GITHUB_EVENT_NAME") != "pull_request":
        return
    continuation = manifest["canonical_continuation"]
    base_ref = env.get("GITHUB_BASE_REF", "")
    head_ref = env.get("GITHUB_HEAD_REF", "")
    _require(base_ref != "main", "category-leadership work must never target main")

    if base_ref == continuation["base_branch"]:
        _require(
            head_ref == continuation["head_branch"],
            f"unexpected PR head: {head_ref!r}",
        )
        return

    if base_ref == continuation["head_branch"]:
        _require(bool(head_ref), "composition PR head is required")
        _require(
            head_ref not in {
                "main",
                continuation["head_branch"],
                continuation["base_branch"],
            },
            f"unexpected composition PR head: {head_ref!r}",
        )
        return

    raise LineageValidationError(f"unexpected PR base: {base_ref!r}")


def validate_git_lineage(repo_root: Path, manifest: Mapping[str, Any]) -> None:
    continuation = manifest["canonical_continuation"]
    rolling = manifest["rolling_parent"]

    category_tip = _fetch_remote_branch(repo_root, continuation["head_branch"])
    rolling_tip = _fetch_remote_branch(repo_root, rolling["branch"])
    _require(
        _is_ancestor(repo_root, rolling_tip, category_tip),
        f"rolling product-completion tip {rolling_tip} is not contained in category tip {category_tip}",
    )

    for anchor in manifest["immutable_anchors"]:
        remote_tip = _fetch_remote_branch(repo_root, anchor["branch"])
        _require(
            remote_tip == anchor["head_sha"],
            f"immutable anchor {anchor['name']} drifted: expected {anchor['head_sha']}, got {remote_tip}",
        )
        if anchor["must_be_ancestor_of_category_head"]:
            _require(
                _is_ancestor(repo_root, anchor["head_sha"], category_tip),
                f"required anchor {anchor['name']} is no longer an ancestor of category tip {category_tip}",
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="validate version-controlled lineage/release contracts without remote Git checks",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    manifest = validate_manifest(repo_root)
    if not args.manifest_only:
        validate_pull_request_shape(manifest, os.environ)
        validate_git_lineage(repo_root, manifest)
    print("EAY canonical lineage and production-truth boundary: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LineageValidationError as exc:
        print(f"EAY canonical lineage and production-truth boundary: FAIL: {exc}")
        raise SystemExit(1) from exc
