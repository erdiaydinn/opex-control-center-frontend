#!/usr/bin/env python3
"""Replace SHA-keyed concurrency on Roadmap 1-15..1-25 exact-head gates.

Exact-head checkout/evidence semantics remain unchanged. Only the concurrency
identity changes so newer commits on the same PR can cancel superseded runs.
Re-runs are idempotent; any third/unreviewed concurrency state fails closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
FILES = [f"eay-roadmap-1-{item}-exact-head.yml" for item in range(15, 26)]
STABLE = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
SHA_EXPR = "${{ github.event.pull_request.head.sha || github.sha }}"


def old_group(item: int) -> str:
    return f"group: eay-roadmap-1-{item}-exact-{SHA_EXPR}"


def apply() -> None:
    for item in range(15, 26):
        name = f"eay-roadmap-1-{item}-exact-head.yml"
        path = WF / name
        text = path.read_text(encoding="utf-8")
        old = old_group(item)
        old_count = text.count(old)
        stable_count = text.count(STABLE)
        if old_count == 1:
            text = text.replace(old, STABLE, 1)
        elif old_count == 0 and stable_count == 1:
            pass
        else:
            raise SystemExit(
                f"{name}: concurrency is neither reviewed SHA state nor stable state"
            )
        path.write_text(text, encoding="utf-8")


def check() -> None:
    failures: list[str] = []
    for name in FILES:
        text = (WF / name).read_text(encoding="utf-8")
        header = text.split("env:", 1)[0]
        if "head.sha || github.sha" in header:
            failures.append(f"{name}: SHA-keyed concurrency remains")
        if STABLE not in header:
            failures.append(f"{name}: stable workflow+PR concurrency missing")
        # These historical gates remain product-completion-only; this script
        # must never broaden their admission to the category branch.
        trigger = text.split("permissions:", 1)[0]
        if "product/eay-category-leadership-v1" in trigger:
            failures.append(f"{name}: unexpected category-leadership PR trigger")
        if "product/eay-product-completion-v1" not in trigger:
            failures.append(f"{name}: product-completion trigger was lost")
        env_block = text.split("env:", 1)[1].split("jobs:", 1)[0]
        if SHA_EXPR not in env_block:
            failures.append(f"{name}: exact-head env binding was changed")

    if failures:
        raise SystemExit("Exact-head concurrency verification failed:\n- " + "\n- ".join(failures))

    print("EXACT_HEAD_15_25_CONCURRENCY=PASS")
    print("superseded_sha_groups=false")
    print("exact_head_checkout_semantics=preserved")
    print("product_completion_admission=preserved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        apply()
    check()


if __name__ == "__main__":
    main()
