#!/usr/bin/env python3
"""Migrate historical Roadmap 1-10..1-14 exact-head workflow headers only.

This intentionally does not touch jobs or exact-head checkout semantics. It
removes the category-leadership PR trigger from historical gates and replaces
SHA-keyed concurrency with a stable workflow+PR key so superseded runs can be
cancelled. Re-runs are idempotent, but any third/unreviewed state fails closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
ITEMS = range(10, 15)
STABLE = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
SHA_EXPR = "${{ github.event.pull_request.head.sha || github.sha }}"

OLD_BRANCHES = """  pull_request:\n    branches:\n      - product/eay-product-completion-v1\n      - product/eay-category-leadership-v1\n"""
NEW_BRANCHES = """  pull_request:\n    branches:\n      - product/eay-product-completion-v1\n"""


def path_for(item: int) -> Path:
    return WF / f"eay-roadmap-1-{item}-exact-head.yml"


def apply() -> None:
    for item in ITEMS:
        path = path_for(item)
        text = path.read_text(encoding="utf-8")

        old_branches = text.count(OLD_BRANCHES)
        new_branches = text.count(NEW_BRANCHES)
        if old_branches == 1:
            text = text.replace(OLD_BRANCHES, NEW_BRANCHES, 1)
        elif old_branches == 0 and new_branches == 1:
            pass
        else:
            raise SystemExit(
                f"{path.name}: PR branch block is neither reviewed old nor reviewed new state"
            )

        old_group = f"group: eay-roadmap-1-{item}-exact-{SHA_EXPR}"
        old_groups = text.count(old_group)
        stable_groups = text.count(STABLE)
        if old_groups == 1:
            text = text.replace(old_group, STABLE, 1)
        elif old_groups == 0 and stable_groups == 1:
            pass
        else:
            raise SystemExit(
                f"{path.name}: concurrency is neither reviewed SHA state nor stable state"
            )

        path.write_text(text, encoding="utf-8")


def check() -> None:
    failures: list[str] = []
    for item in ITEMS:
        path = path_for(item)
        text = path.read_text(encoding="utf-8")
        trigger = text.split("permissions:", 1)[0]
        concurrency = text.split("env:", 1)[0]
        env_block = text.split("env:", 1)[1].split("jobs:", 1)[0]

        if "product/eay-category-leadership-v1" in trigger:
            failures.append(f"{path.name}: category-leadership PR trigger remains")
        if "product/eay-product-completion-v1" not in trigger:
            failures.append(f"{path.name}: product-completion PR trigger lost")
        if STABLE not in concurrency:
            failures.append(f"{path.name}: stable workflow+PR concurrency missing")
        if "head.sha || github.sha" in concurrency:
            failures.append(f"{path.name}: SHA-keyed concurrency remains")
        if SHA_EXPR not in env_block:
            failures.append(f"{path.name}: exact-head env binding was changed")

    if failures:
        raise SystemExit("Legacy exact-head header verification failed:\n- " + "\n- ".join(failures))

    print("LEGACY_EXACT_HEAD_10_14=PASS")
    print("category_pr_fanout=false")
    print("superseded_sha_groups=false")
    print("exact_head_env_binding=preserved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        apply()
    check()


if __name__ == "__main__":
    main()
