#!/usr/bin/env python3
"""Apply and verify EAY GitHub Actions CI admission-control policy.

This script is intentionally fail-closed: every mutation requires the exact
pre-change fragment that was reviewed on the canonical base. If repository
structure drifts, it exits instead of guessing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"

LEGACY = [
    "eay-roadmap-1-10-acceptance.yml",
    "eay-roadmap-1-10-exact-head.yml",
    "eay-roadmap-1-11-exact-head.yml",
    "eay-roadmap-1-12-exact-head.yml",
    "eay-roadmap-1-13-exact-head.yml",
    "eay-roadmap-1-14-exact-head.yml",
]
EXACT = LEGACY[1:]

PLANOGRAM = [
    "eay-master-roadmap-24-planogram-physical-truth.yml",
    "eay-master-roadmap-25-planogram-optimizer.yml",
    "eay-master-roadmap-26-planogram-execution-compliance.yml",
    "eay-master-roadmap-24-27-cumulative-exact-head.yml",
]
BUDGET = "eay-master-roadmap-28-budget-planning-engine.yml"
DOCKOS = "dockos-full-stack.yml"
JARVIS = "jarvis-convergence-ci.yml"

LEGACY_PR_OLD = """  pull_request:
    branches:
      - product/eay-product-completion-v1
      - product/eay-category-leadership-v1
"""
LEGACY_PR_NEW = """  pull_request:
    branches:
      - product/eay-product-completion-v1
"""

PLANOGRAM_PR_OLD = """  pull_request:
    branches:
      - product/eay-category-leadership-v1
"""
PLANOGRAM_PR_NEW = """  pull_request:
    branches:
      - product/eay-category-leadership-v1
    paths:
      - "apps/planai/**"
      - "services/core-api/**/planogram/**"
      - "services/core-api/**/planogram*.py"
      - "services/core-api/alembic/**"
      - "src/**/*planogram*"
      - "src/**/Planogram/**"
      - "config/**/*planogram*"
      - "scripts/**/*planogram*"
      - ".github/workflows/eay-master-roadmap-24-planogram-physical-truth.yml"
      - ".github/workflows/eay-master-roadmap-25-planogram-optimizer.yml"
      - ".github/workflows/eay-master-roadmap-26-planogram-execution-compliance.yml"
      - ".github/workflows/eay-master-roadmap-24-27-cumulative-exact-head.yml"
"""

BUDGET_PR_OLD = """  pull_request:
    branches: [product/eay-category-leadership-v1]
"""
BUDGET_PR_NEW = """  pull_request:
    branches: [product/eay-category-leadership-v1]
    paths:
      - "backend/**/*budget*"
      - "backend/**/budget/**"
      - "services/core-api/**/*budget*"
      - "services/core-api/**/budget/**"
      - "src/**/*budget*"
      - "src/**/Budget/**"
      - "config/**/*budget*"
      - "scripts/**/*budget*"
      - ".github/workflows/eay-master-roadmap-28-budget-planning-engine.yml"
"""

DOCKOS_PR_OLD = """  pull_request:
  workflow_dispatch:
"""
DOCKOS_PR_NEW = """  pull_request:
    paths:
      - "backend/**"
      - "src/**/*workforce*"
      - "src/**/Workforce/**"
      - "src/**/*dockos*"
      - "src/**/DockOS/**"
      - "src/**/*hiring*"
      - "src/**/Hiring/**"
      - "package.json"
      - "package-lock.json"
      - ".github/workflows/dockos-full-stack.yml"
  workflow_dispatch:
"""

JARVIS_PATHS_OLD = """    paths:
      - "services/core-api/**"
      - "services/eay-ai-core/**"
      - ".github/workflows/jarvis-convergence-ci.yml"
"""
JARVIS_PATHS_NEW = """    paths:
      - "services/core-api/app/ai_tool_routes.py"
      - "services/core-api/app/main.py"
      - "services/core-api/app/core/ai_*.py"
      - "services/core-api/app/core/permission_catalog.py"
      - "services/core-api/tests/test_ai_*.py"
      - "services/core-api/tests/test_security_foundation.py"
      - "services/core-api/tests/test_sql_access_boundary.py"
      - "services/core-api/alembic/**"
      - "services/core-api/pyproject.toml"
      - "services/eay-ai-core/**"
      - ".github/workflows/jarvis-convergence-ci.yml"
"""

STABLE_CONCURRENCY = """concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

"""


def read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (WF / name).write_text(text, encoding="utf-8")


def replace_exact(text: str, old: str, new: str, *, count: int, label: str) -> str:
    found = text.count(old)
    if found != count:
        raise SystemExit(f"{label}: expected {count} reviewed fragment(s), found {found}")
    return text.replace(old, new)


def add_concurrency_before_jobs(text: str, *, label: str) -> str:
    if "\nconcurrency:\n" in text:
        return text
    marker = "\njobs:\n"
    if text.count(marker) != 1:
        raise SystemExit(f"{label}: expected exactly one jobs marker")
    return text.replace(marker, "\n" + STABLE_CONCURRENCY + "jobs:\n", 1)


def apply() -> None:
    # Historical 1-10..1-14 gates remain available on product-completion and
    # workflow_dispatch, but no longer fan out on every category-leadership PR.
    for name in LEGACY:
        text = read(name)
        text = replace_exact(
            text, LEGACY_PR_OLD, LEGACY_PR_NEW, count=1, label=f"{name} legacy PR scope"
        )
        if name in EXACT:
            old_prefix = f"group: eay-roadmap-{name.removeprefix('eay-roadmap-').removesuffix('-exact-head.yml')}-exact-"
            old_group = old_prefix + "${{ github.event.pull_request.head.sha || github.sha }}"
            new_group = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
            text = replace_exact(
                text, old_group, new_group, count=1, label=f"{name} concurrency"
            )
        write(name, text)

    # Domain-heavy PR gates are scoped to their domain. Canonical branch pushes
    # intentionally stay broad so cumulative regression still runs after compose.
    for name in PLANOGRAM:
        text = read(name)
        text = replace_exact(
            text, PLANOGRAM_PR_OLD, PLANOGRAM_PR_NEW, count=1, label=f"{name} PR paths"
        )
        if name != "eay-master-roadmap-24-27-cumulative-exact-head.yml":
            text = add_concurrency_before_jobs(text, label=f"{name} concurrency")
        write(name, text)

    text = read(BUDGET)
    text = replace_exact(text, BUDGET_PR_OLD, BUDGET_PR_NEW, count=1, label=f"{BUDGET} PR paths")
    write(BUDGET, text)

    text = read(DOCKOS)
    text = replace_exact(text, DOCKOS_PR_OLD, DOCKOS_PR_NEW, count=1, label=f"{DOCKOS} PR paths")
    text = add_concurrency_before_jobs(text, label=f"{DOCKOS} concurrency")
    write(DOCKOS, text)

    text = read(JARVIS)
    text = replace_exact(
        text, JARVIS_PATHS_OLD, JARVIS_PATHS_NEW, count=2, label=f"{JARVIS} narrow paths"
    )
    write(JARVIS, text)


def check() -> None:
    failures: list[str] = []

    for name in LEGACY:
        text = read(name)
        header = text.split("permissions:", 1)[0]
        if "product/eay-category-leadership-v1" in header:
            failures.append(f"{name}: category-leadership still auto-triggers legacy PR gate")

    for name in EXACT:
        text = read(name)
        if "group: eay-roadmap-" in text and "head.sha || github.sha" in text.split("env:", 1)[0]:
            failures.append(f"{name}: SHA-keyed PR concurrency still present")
        stable = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
        if stable not in text:
            failures.append(f"{name}: stable PR concurrency missing")

    for name in PLANOGRAM:
        text = read(name)
        pr_block = text.split("  pull_request:", 1)[1].split("\n\n", 1)[0]
        if "    paths:" not in pr_block:
            failures.append(f"{name}: PR path admission missing")

    budget = read(BUDGET)
    if "    paths:" not in budget.split("  pull_request:", 1)[1].split("  workflow_dispatch:", 1)[0]:
        failures.append(f"{BUDGET}: PR path admission missing")

    dockos = read(DOCKOS)
    if "  pull_request:\n    paths:" not in dockos:
        failures.append(f"{DOCKOS}: global pull_request fan-out still present")
    stable = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
    if stable not in dockos:
        failures.append(f"{DOCKOS}: stable concurrency missing")

    jarvis = read(JARVIS)
    if '- "services/core-api/**"' in jarvis:
        failures.append(f"{JARVIS}: broad Core API path still present")
    if jarvis.count('- "services/core-api/app/core/ai_*.py"') != 2:
        failures.append(f"{JARVIS}: narrowed Orders/Jarvis paths not present on push and PR")

    if failures:
        raise SystemExit("CI admission-control verification failed:\n- " + "\n- ".join(failures))

    print("CI_ADMISSION_CONTROL=PASS")
    print("legacy_category_pr_fanout=false")
    print("superseded_pr_sha_concurrency=false")
    print("domain_heavy_pr_paths=scoped")
    print("canonical_push_cumulative_regression=preserved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        apply()
    check()


if __name__ == "__main__":
    main()
