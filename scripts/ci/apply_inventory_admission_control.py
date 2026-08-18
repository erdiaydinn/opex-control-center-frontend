#!/usr/bin/env python3
"""Align Inventory and DockOS PR admission without reducing regression coverage.

Run after apply_ci_admission_control.py. Inventory changes are routed to the
Inventory Production Gate; DockOS remains responsible for Workforce,
Recruitment and DockOS. Android's standalone gate keeps its existing scope but
gains stable concurrency so superseded PR/push runs can be cancelled.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
DOCKOS = WF / "dockos-full-stack.yml"
INVENTORY = WF / "eay-inventory-production.yml"
ANDROID = WF / "opex-inventory-android.yml"
STABLE = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
CONCURRENCY = f"""concurrency:\n  {STABLE}\n  cancel-in-progress: true\n\n"""

DOCKOS_INVENTORY_LINES = [
    '      - "backend/app/modules/inventory/**"\n',
    '      - "backend/migrations/*inventory*.sql"\n',
    '      - "src/**/*inventory*"\n',
    '      - "src/**/Inventory/**"\n',
]

INV_PR_OLD = """  pull_request:\n    branches:\n      - release/platform-convergence-v0.1\n"""
INV_PR_NEW = """  pull_request:\n    branches:\n      - product/eay-category-leadership-v1\n      - release/platform-convergence-v0.1\n"""


def add_concurrency(text: str, label: str) -> str:
    if "\nconcurrency:\n" in text:
        if STABLE not in text:
            raise SystemExit(f"{label}: unexpected pre-existing concurrency")
        return text
    marker = "\njobs:\n"
    if text.count(marker) != 1:
        raise SystemExit(f"{label}: expected exactly one jobs marker")
    return text.replace(marker, "\n" + CONCURRENCY + "jobs:\n", 1)


def apply() -> None:
    dockos = DOCKOS.read_text(encoding="utf-8")
    for line in DOCKOS_INVENTORY_LINES:
        if dockos.count(line) != 1:
            raise SystemExit(f"dockos: expected one reviewed Inventory admission line: {line.strip()}")
        dockos = dockos.replace(line, "", 1)
    DOCKOS.write_text(dockos, encoding="utf-8")

    inv = INVENTORY.read_text(encoding="utf-8")
    if inv.count(INV_PR_OLD) != 1:
        raise SystemExit("inventory production: reviewed PR branch block drifted")
    inv = inv.replace(INV_PR_OLD, INV_PR_NEW, 1)
    inv = add_concurrency(inv, "inventory production")
    INVENTORY.write_text(inv, encoding="utf-8")

    android = ANDROID.read_text(encoding="utf-8")
    android = add_concurrency(android, "inventory android")
    ANDROID.write_text(android, encoding="utf-8")


def check() -> None:
    failures: list[str] = []
    dockos = DOCKOS.read_text(encoding="utf-8")
    dockos_pr = dockos.split("  pull_request:\n", 1)[1].split("  workflow_dispatch:\n", 1)[0]
    for forbidden in (
        "backend/app/modules/inventory/**",
        "backend/migrations/*inventory*.sql",
        "src/**/*inventory*",
        "src/**/Inventory/**",
    ):
        if forbidden in dockos_pr:
            failures.append(f"dockos still admits Inventory PR changes: {forbidden}")

    inv = INVENTORY.read_text(encoding="utf-8")
    inv_pr = inv.split("  pull_request:\n", 1)[1].split("  push:\n", 1)[0]
    if "product/eay-category-leadership-v1" not in inv_pr:
        failures.append("Inventory Production Gate is not enabled for category PRs")
    if "release/platform-convergence-v0.1" not in inv_pr:
        failures.append("Inventory Production Gate lost release PR admission")
    if STABLE not in inv:
        failures.append("Inventory Production Gate lacks stable concurrency")

    android = ANDROID.read_text(encoding="utf-8")
    if STABLE not in android:
        failures.append("Inventory Android gate lacks stable concurrency")
    android_pr = android.split("  pull_request:\n", 1)[1].split("\n\npermissions:", 1)[0]
    if '"android-inventory/**"' not in android_pr:
        failures.append("Inventory Android gate lost Android path scope")

    if failures:
        raise SystemExit("Inventory admission verification failed:\n- " + "\n- ".join(failures))

    print("INVENTORY_ADMISSION_CONTROL=PASS")
    print("dockos_inventory_fanout=false")
    print("inventory_category_pr_gate=true")
    print("inventory_android_scope=preserved")
    print("inventory_superseded_runs_cancellable=true")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        apply()
    check()


if __name__ == "__main__":
    main()
