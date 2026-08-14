#!/usr/bin/env python3
"""Fail-closed validator for the version-locked EAY release candidate.

EAY ships more than one deployable from this repository. The AI service line and
the platform application line therefore must not be forced into one source tree.
This validator locks every canonical ref, verifies required ancestry globally, and
only performs virtual Git composition inside deployables that are actually meant
to share one release tree.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REVISION_RE = re.compile(
    r"^revision(?:\s*:\s*str)?\s*=\s*[\"']([^\"']+)[\"']",
    re.MULTILINE,
)


def run(
    args: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        check=False,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "EAY RC Validator",
            "GIT_AUTHOR_EMAIL": "eay-rc-validator@localhost",
            "GIT_COMMITTER_NAME": "EAY RC Validator",
            "GIT_COMMITTER_EMAIL": "eay-rc-validator@localhost",
        },
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def fetch_locked(branch: str, expected_sha: str) -> str:
    remote_ref = f"refs/remotes/origin/{branch}"
    run(
        [
            "git",
            "fetch",
            "--no-tags",
            "--force",
            "origin",
            f"+refs/heads/{branch}:{remote_ref}",
        ]
    )
    actual = run(["git", "rev-parse", remote_ref]).stdout.strip()
    if actual != expected_sha:
        raise ValueError(
            f"head drift for {branch}: locked={expected_sha} actual={actual}"
        )
    run(["git", "cat-file", "-e", f"{expected_sha}^{{commit}}"])
    return actual


def is_ancestor(ancestor: str, descendant: str) -> bool:
    return (
        run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
        ).returncode
        == 0
    )


def virtual_merge(
    current: str,
    component: str,
    label: str,
) -> tuple[str | None, str | None]:
    if current == component or is_ancestor(component, current):
        return current, None
    if is_ancestor(current, component):
        return component, None

    merged = run(
        ["git", "merge-tree", "--write-tree", current, component],
        check=False,
    )
    if merged.returncode != 0:
        detail = (merged.stdout + "\n" + merged.stderr).strip()
        return None, detail[:30000]

    lines = [line.strip() for line in merged.stdout.splitlines() if line.strip()]
    if not lines or not SHA_RE.fullmatch(lines[0]):
        return None, f"unexpected merge-tree output for {label}: {merged.stdout[:5000]}"

    tree_sha = lines[0]
    commit = run(
        ["git", "commit-tree", tree_sha, "-p", current, "-p", component],
        input_text=f"virtual EAY RC compose: {label}\n",
    ).stdout.strip()
    if not SHA_RE.fullmatch(commit):
        return None, f"invalid synthetic commit for {label}: {commit!r}"
    return commit, None


def detect_duplicate_alembic_revisions(commit_sha: str) -> list[str]:
    listing = run(["git", "ls-tree", "-r", "--name-only", commit_sha]).stdout.splitlines()
    version_paths = [
        path
        for path in listing
        if path.startswith("services/core-api/alembic/versions/")
        and path.endswith(".py")
    ]
    seen: dict[str, str] = {}
    errors: list[str] = []
    for path in version_paths:
        content = run(["git", "show", f"{commit_sha}:{path}"]).stdout
        match = REVISION_RE.search(content)
        if not match:
            continue
        revision = match.group(1)
        prior = seen.get(revision)
        if prior and prior != path:
            errors.append(
                f"duplicate Alembic revision {revision}: {prior} and {path}"
            )
        else:
            seen[revision] = path
    return errors


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 2:
        raise ValueError("unsupported release manifest schema")
    if data.get("production_ready") is not False:
        raise ValueError(
            "release manifest must remain production_ready=false before external acceptance"
        )
    if data.get("main_merge_permitted") is not False:
        raise ValueError("release manifest must remain main_merge_permitted=false")
    if not isinstance(data.get("deployables"), dict) or not data["deployables"]:
        raise ValueError("release manifest must define deployables")
    return data


def validate_ref(
    item: dict[str, Any],
    *,
    result: dict[str, Any],
    refs: dict[str, dict[str, Any]],
    branches: set[str],
) -> None:
    key = item.get("key")
    branch = item.get("branch")
    sha = item.get("sha")
    pr = item.get("pr")

    if not isinstance(key, str) or not key:
        result["errors"].append("release ref missing key")
        return
    if key in refs:
        result["errors"].append(f"duplicate release ref key: {key}")
        return
    if not isinstance(branch, str) or not branch:
        result["errors"].append(f"{key}: invalid branch")
        return
    if branch in branches:
        result["errors"].append(f"duplicate release ref branch: {branch}")
        return
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        result["errors"].append(f"{key}: invalid locked SHA")
        return
    if pr is not None and (not isinstance(pr, int) or pr <= 0):
        result["errors"].append(f"{key}: invalid PR number")
        return

    refs[key] = item
    branches.add(branch)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="config/eay_release_candidate_v0_1.json")
    parser.add_argument("--result", default="eay-rc-composition-result.json")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    result: dict[str, Any] = {
        "candidate_id": manifest["candidate_id"],
        "production_ready": False,
        "main_merge_permitted": False,
        "locked_heads": {},
        "ancestry": [],
        "deployables": {},
        "errors": [],
    }

    refs: dict[str, dict[str, Any]] = {}
    branches: set[str] = set()

    for item in manifest.get("lineage_refs", []):
        validate_ref(item, result=result, refs=refs, branches=branches)

    for deployable_name, deployable in manifest["deployables"].items():
        if not isinstance(deployable, dict):
            result["errors"].append(f"{deployable_name}: invalid deployable definition")
            continue
        for component in deployable.get("components", []):
            validate_ref(component, result=result, refs=refs, branches=branches)

    if result["errors"]:
        Path(args.result).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 1

    try:
        for key, item in refs.items():
            result["locked_heads"][key] = fetch_locked(item["branch"], item["sha"])
    except Exception as exc:
        result["errors"].append(str(exc))
        Path(args.result).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 1

    for rule in manifest.get("required_ancestry", []):
        ancestor_key = rule.get("ancestor_key")
        descendant_key = rule.get("descendant_key")
        if ancestor_key not in refs or descendant_key not in refs:
            result["errors"].append(
                f"ancestry rule references unknown ref: {ancestor_key}->{descendant_key}"
            )
            continue
        passed = is_ancestor(refs[ancestor_key]["sha"], refs[descendant_key]["sha"])
        result["ancestry"].append(
            {
                "ancestor_key": ancestor_key,
                "descendant_key": descendant_key,
                "passed": passed,
                "reason": rule.get("reason", ""),
            }
        )
        if not passed:
            result["errors"].append(
                f"ancestry violation: {descendant_key} does not contain {ancestor_key}"
            )

    for deployable_name, deployable in manifest["deployables"].items():
        mode = deployable.get("mode")
        component_keys = [item["key"] for item in deployable.get("components", [])]
        deployable_result: dict[str, Any] = {
            "mode": mode,
            "components": component_keys,
            "composition": [],
            "errors": [],
        }
        result["deployables"][deployable_name] = deployable_result

        if mode == "ancestry_release":
            release_key = deployable.get("release_key")
            if release_key not in component_keys or release_key not in refs:
                message = f"{deployable_name}: invalid release_key {release_key!r}"
                deployable_result["errors"].append(message)
                result["errors"].append(message)
                continue
            deployable_result["artifact_head"] = refs[release_key]["sha"]
            deployable_result["repository_integration_ready"] = not deployable_result[
                "errors"
            ]
            continue

        if mode != "virtual_merge":
            message = f"{deployable_name}: unsupported mode {mode!r}"
            deployable_result["errors"].append(message)
            result["errors"].append(message)
            continue

        base_key = deployable.get("base_key")
        if base_key not in component_keys or base_key not in refs:
            message = f"{deployable_name}: invalid base_key {base_key!r}"
            deployable_result["errors"].append(message)
            result["errors"].append(message)
            continue

        current = refs[base_key]["sha"]
        for key in deployable.get("composition_order", []):
            if key == base_key or key not in component_keys or key not in refs:
                message = f"{deployable_name}: invalid composition component {key!r}"
                deployable_result["errors"].append(message)
                result["errors"].append(message)
                break

            next_commit, conflict = virtual_merge(current, refs[key]["sha"], key)
            entry: dict[str, Any] = {
                "component": key,
                "input_sha": refs[key]["sha"],
                "base_before": current,
                "passed": conflict is None,
            }
            if conflict is not None:
                entry["conflict"] = conflict
                deployable_result["composition"].append(entry)
                message = f"{deployable_name}: virtual composition conflict at {key}"
                deployable_result["errors"].append(message)
                result["errors"].append(message)
                break

            assert next_commit is not None
            current = next_commit
            entry["synthetic_head_after"] = current
            deployable_result["composition"].append(entry)

        if not deployable_result["errors"]:
            if deployable.get("check_alembic_revisions") is True:
                migration_errors = detect_duplicate_alembic_revisions(current)
                deployable_result["errors"].extend(migration_errors)
                result["errors"].extend(migration_errors)
            deployable_result["synthetic_composition_head"] = current

        deployable_result["repository_integration_ready"] = not deployable_result[
            "errors"
        ]

    result["external_acceptance_blockers"] = manifest.get(
        "external_acceptance_blockers", {}
    )
    result["repository_integration_ready"] = not result["errors"]

    Path(args.result).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
