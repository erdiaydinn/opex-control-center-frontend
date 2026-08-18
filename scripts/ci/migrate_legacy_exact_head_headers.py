#!/usr/bin/env python3
"""Normalize historical Roadmap 1-10..1-25 exact-head workflow headers.

This migration intentionally touches header admission/concurrency only. Job
bodies and exact-head checkout semantics remain unchanged. It is idempotent so
runner retries cannot corrupt already-migrated files, and it fails closed on
unexpected trigger/concurrency drift.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
STABLE = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
SHA_EXPR = "${{ github.event.pull_request.head.sha || github.sha }}"
PRODUCT = "product/eay-product-completion-v1"
CATEGORY = "product/eay-category-leadership-v1"
CATEGORY_LINE = "      - product/eay-category-leadership-v1\n"


def path_for(item: int) -> Path:
    return WF / f"eay-roadmap-1-{item}-exact-head.yml"


def trigger_block(text: str) -> str:
    if "permissions:" not in text:
        raise SystemExit("workflow header missing permissions boundary")
    return text.split("permissions:", 1)[0]


def normalize_item(item: int, *, write: bool) -> None:
    path = path_for(item)
    text = path.read_text(encoding="utf-8")
    trigger = trigger_block(text)

    # Accept both reviewed YAML spellings: multi-line branches and inline list.
    if PRODUCT not in trigger:
        raise SystemExit(f"{path.name}: product-completion PR trigger missing")

    if item <= 14:
        category_count = trigger.count(CATEGORY)
        if category_count == 1:
            if CATEGORY_LINE not in trigger:
                raise SystemExit(
                    f"{path.name}: category trigger exists in an unreviewed YAML shape"
                )
            text = text.replace(CATEGORY_LINE, "", 1)
        elif category_count != 0:
            raise SystemExit(f"{path.name}: unexpected category trigger count={category_count}")
    elif CATEGORY in trigger:
        raise SystemExit(f"{path.name}: unexpected category-leadership PR trigger")

    old_group = f"group: eay-roadmap-1-{item}-exact-{SHA_EXPR}"
    old_count = text.count(old_group)
    stable_count = text.count(STABLE)
    if old_count == 1 and stable_count == 0:
        text = text.replace(old_group, STABLE, 1)
    elif old_count == 0 and stable_count == 1:
        pass
    else:
        raise SystemExit(
            f"{path.name}: unexpected concurrency state old={old_count} stable={stable_count}"
        )

    if write:
        path.write_text(text, encoding="utf-8")


def apply() -> None:
    for item in range(10, 26):
        normalize_item(item, write=True)


def check() -> None:
    failures: list[str] = []
    for item in range(10, 26):
        path = path_for(item)
        text = path.read_text(encoding="utf-8")
        trigger = trigger_block(text)
        header = text.split("env:", 1)[0] if "env:" in text else text.split("jobs:", 1)[0]

        if PRODUCT not in trigger:
            failures.append(f"{path.name}: product-completion trigger lost")
        if CATEGORY in trigger:
            failures.append(f"{path.name}: category-leadership PR trigger remains")
        if STABLE not in header:
            failures.append(f"{path.name}: stable workflow+PR concurrency missing")
        if "head.sha || github.sha" in header:
            failures.append(f"{path.name}: SHA-keyed concurrency remains")
        if "env:" in text:
            env_block = text.split("env:", 1)[1].split("jobs:", 1)[0]
            if SHA_EXPR not in env_block:
                failures.append(f"{path.name}: exact-head env binding changed")

    if failures:
        raise SystemExit("Historical exact-head verification failed:\n- " + "\n- ".join(failures))

    print("HISTORICAL_EXACT_HEAD_10_25=PASS")
    print("category_pr_fanout_10_14=false")
    print("superseded_sha_groups_10_25=false")
    print("exact_head_checkout_semantics=preserved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        apply()
    check()


if __name__ == "__main__":
    main()
