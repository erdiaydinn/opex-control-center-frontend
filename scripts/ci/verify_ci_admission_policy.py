#!/usr/bin/env python3
"""Read-only verifier for the EAY GitHub Actions admission policy.

The verifier supports both legitimate repository phases:
- canonical through Master 55, where the 56-60 Release Authority workflow is
  not yet present; and
- a later composed tree where that workflow exists and must remain path-scoped.

It never mutates files.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
STABLE = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"


def read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def pr_block(text: str, next_marker: str | None = None) -> str:
    block = text.split("  pull_request:\n", 1)[1]
    if next_marker and next_marker in block:
        return block.split(next_marker, 1)[0]
    return block.split("\n\n", 1)[0]


def main() -> None:
    failures: list[str] = []

    legacy = read("eay-roadmap-1-10-acceptance.yml")
    legacy_trigger = legacy.split("permissions:", 1)[0]
    if "product/eay-category-leadership-v1" in legacy_trigger:
        failures.append("legacy 1-10 acceptance still auto-triggers category PRs")
    if "product/eay-product-completion-v1" not in legacy_trigger:
        failures.append("legacy 1-10 acceptance lost product-completion PR admission")

    planogram = [
        "eay-master-roadmap-24-planogram-physical-truth.yml",
        "eay-master-roadmap-25-planogram-optimizer.yml",
        "eay-master-roadmap-26-planogram-execution-compliance.yml",
        "eay-master-roadmap-24-27-cumulative-exact-head.yml",
    ]
    for name in planogram:
        text = read(name)
        block = pr_block(text)
        if "    paths:" not in block:
            failures.append(f"{name}: PR path admission missing")
        if '"apps/planai/**"' not in block:
            failures.append(f"{name}: PlanAI path admission missing")
        if '"services/core-api/alembic/**"' in block:
            failures.append(f"{name}: broad migration path would reintroduce fan-out")

    budget = read("eay-master-roadmap-28-budget-planning-engine.yml")
    budget_pr = pr_block(budget, "  workflow_dispatch:\n")
    if "    paths:" not in budget_pr:
        failures.append("Budget 28-30 PR path admission missing")
    if '"backend/app/modules/budget/**"' not in budget_pr:
        failures.append("Budget 28-30 domain path missing")

    dockos = read("dockos-full-stack.yml")
    dockos_pr = pr_block(dockos, "  workflow_dispatch:\n")
    if "    paths:" not in dockos_pr:
        failures.append("DockOS still has global pull_request admission")
    for forbidden in (
        '"backend/app/modules/inventory/**"',
        '"backend/migrations/*inventory*.sql"',
        '"src/**/*inventory*"',
        '"src/**/Inventory/**"',
    ):
        if forbidden in dockos_pr:
            failures.append(f"DockOS still consumes Inventory PR admission: {forbidden}")
    if STABLE not in dockos:
        failures.append("DockOS stable workflow+PR concurrency missing")

    inventory = read("eay-inventory-production.yml")
    inventory_pr = pr_block(inventory, "  push:\n")
    if "product/eay-category-leadership-v1" not in inventory_pr:
        failures.append("Inventory Production Gate not enabled for category PRs")
    if "release/platform-convergence-v0.1" not in inventory_pr:
        failures.append("Inventory Production Gate lost release PR admission")
    if STABLE not in inventory:
        failures.append("Inventory Production Gate stable concurrency missing")

    android = read("opex-inventory-android.yml")
    android_pr = pr_block(android, "\n\npermissions:\n")
    if '"android-inventory/**"' not in android_pr:
        failures.append("Inventory Android gate lost Android path scope")
    if STABLE not in android:
        failures.append("Inventory Android stable concurrency missing")

    jarvis = read("jarvis-convergence-ci.yml")
    if '- "services/core-api/**"' in jarvis:
        failures.append("Jarvis Orders V2 still admits the whole Core API")
    if jarvis.count('- "services/core-api/app/core/ai_*.py"') != 2:
        failures.append("Jarvis narrowed AI path must exist on both push and PR")
    if '- "services/core-api/alembic/**"' in jarvis:
        failures.append("Jarvis still admits all Core migrations")

    # Master 56-60 is legitimately absent on the current Master55 canonical
    # base. Once composed, it must retain its reviewed release-only admission.
    release_path = WF / "eay-master-roadmap-56-60-release-leadership.yml"
    if release_path.exists():
        release = release_path.read_text(encoding="utf-8")
        release_header = release.split("permissions:", 1)[0]
        if "paths:" not in release_header:
            failures.append("Release Authority lost path-scoped admission")
        if "group: eay-master-56-60-${{ github.ref }}" not in release:
            failures.append("Release Authority concurrency changed unexpectedly")
        print("release_authority_phase=composed_and_verified")
    else:
        print("release_authority_phase=pre_56_60_canonical_expected_absence")

    guard = read("ci-admission-guard.yml")
    if "contents: read" not in guard:
        failures.append("CI Admission Guard must remain read-only")
    if STABLE not in guard:
        failures.append("CI Admission Guard stable concurrency missing")

    if failures:
        raise SystemExit("CI admission policy verification failed:\n- " + "\n- ".join(failures))

    print("CI_ADMISSION_POLICY=PASS")
    print("legacy_category_pr_fanout=false")
    print("domain_heavy_pr_admission=scoped")
    print("dockos_inventory_fanout=false")
    print("jarvis_core_api_fanout=false")
    print("canonical_push_regression=preserved")


if __name__ == "__main__":
    main()
