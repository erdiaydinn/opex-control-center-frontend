#!/usr/bin/env python3
"""Fail-closed validator for the version-locked EAY release candidate.

The validator never mutates a remote branch. It fetches the exact canonical refs,
checks locked-head drift and required ancestry, then uses `git merge-tree` plus
`git commit-tree` to build an ephemeral multi-parent composition locally. Any
merge conflict blocks the release candidate before staging.
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
REVISION_RE = re.compile(r"^revision(?:\s*:\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def run(args: list[str], *, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
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
        raise ValueError(f"head drift for {branch}: locked={expected_sha} actual={actual}")
    run(["git", "cat-file", "-e", f"{expected_sha}^{{commit}}"])
    return actual


def is_ancestor(ancestor: str, descendant: str) -> bool:
    return run(["git", "merge-base", "--is-ancestor", ancestor, descendant], check=False).returncode == 0


def virtual_merge(current: str, component: str, label: str) -> tuple[str | None, str | None]:
    if current == component or is_ancestor(component, current):
        return current, None
    if is_ancestor(current, component):
        return component, None

    merged = run(["git", "merge-tree", "--write-tree", current, component], check=False)
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
        p for p in listing if p.startswith("services/core-api/alembic/versions/") and p.endswith(".py")
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
            errors.append(f"duplicate Alembic revision {revision}: {prior} and {path}")
        else:
            seen[revision] = path
    return errors


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported release manifest schema")
    if data.get("production_ready") is not False:
        raise ValueError("release manifest must remain production_ready=false before external acceptance")
    if data.get("main_merge_permitted") is not False:
        raise ValueError("release manifest must remain main_merge_permitted=false")
    return data


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
        "composition": [],
        "errors": [],
    }

    components = manifest.get("components", [])
    by_key: dict[str, dict[str, Any]] = {}
    branches: set[str] = set()
    prs: set[int] = set()

    for component in components:
        key = component.get("key")
        branch = component.get("branch")
        sha = component.get("sha")
        pr = component.get("pr")
        if not isinstance(key, str) or not key:
            result["errors"].append("component missing key")
            continue
        if key in by_key:
            result["errors"].append(f"duplicate component key: {key}")
        if not isinstance(branch, str) or not branch:
            result["errors"].append(f"{key}: invalid branch")
        elif branch in branches:
            result["errors"].append(f"duplicate component branch: {branch}")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            result["errors"].append(f"{key}: invalid locked SHA")
        if not isinstance(pr, int) or pr <= 0:
            result["errors"].append(f"{key}: invalid PR number")
        elif pr in prs and key != "ai_core":
            result["errors"].append(f"duplicate PR number: {pr}")
        by_key[key] = component
        if isinstance(branch, str):
            branches.add(branch)
        if isinstance(pr, int):
            prs.add(pr)

    security = manifest["frozen_foundations"]["security_core"]
    security_sha = security["sha"]
    if not SHA_RE.fullmatch(security_sha):
        result["errors"].append("invalid frozen Security/Core SHA")

    if result["errors"]:
        Path(args.result).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 1

    try:
        fetch_locked(security["branch"], security_sha)
        result["locked_heads"]["security_core"] = security_sha
        for key, component in by_key.items():
            actual = fetch_locked(component["branch"], component["sha"])
            result["locked_heads"][key] = actual
    except Exception as exc:  # fail closed with machine-readable evidence
        result["errors"].append(str(exc))
        Path(args.result).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 1

    for rule in manifest.get("required_ancestry", []):
        ancestor_key = rule["ancestor_key"]
        descendant_key = rule["descendant_key"]
        ancestor = by_key[ancestor_key]["sha"]
        descendant = by_key[descendant_key]["sha"]
        passed = is_ancestor(ancestor, descendant)
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

    current = security_sha
    for key in manifest.get("composition_order", []):
        component = by_key.get(key)
        if component is None:
            result["errors"].append(f"composition_order references unknown component: {key}")
            break
        next_commit, conflict = virtual_merge(current, component["sha"], key)
        entry: dict[str, Any] = {
            "component": key,
            "input_sha": component["sha"],
            "base_before": current,
            "passed": conflict is None,
        }
        if conflict is not None:
            entry["conflict"] = conflict
            result["composition"].append(entry)
            result["errors"].append(f"virtual composition conflict at {key}")
            break
        assert next_commit is not None
        current = next_commit
        entry["synthetic_head_after"] = current
        result["composition"].append(entry)

    if not result["errors"]:
        result["errors"].extend(detect_duplicate_alembic_revisions(current))
        result["synthetic_composition_head"] = current

    result["external_acceptance_blockers"] = manifest.get("external_acceptance_blockers", {})
    result["repository_integration_ready"] = not result["errors"]

    Path(args.result).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result["errors"]:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
