#!/usr/bin/env python3
"""Apply and verify EAY GitHub Actions CI admission-control policy.

The mutation path is deliberately fail-closed: every rewrite requires an exact
reviewed pre-change fragment from the canonical base. Unexpected repository
drift exits non-zero instead of guessing or weakening a gate.

Policy:
- workstream PRs run scoped delta gates;
- category-canonical pushes keep broad cumulative regression;
- historical Roadmap 1-10..1-14 gates stop auto-running on every category PR;
- PR concurrency is keyed by workflow + PR, never by immutable head SHA, so a
  superseded commit is actually cancellable while jobs still checkout exact SHA;
- global/heavy gates require explicit PR path admission.
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
      - "services/core-api/app/modules/planogram/**"
      - "services/core-api/tests/test_planogram*.py"
      - "services/core-api/alembic/versions/*planogram*.py"
      - "services/core-api/app/budget_main.py"
      - "config/eay_master_roadmap_60.json"
      - "src/**/*planogram*"
      - "src/**/Planogram/**"
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
      - "backend/app/modules/budget/**"
      - "backend/**/*budget*.py"
      - "backend/migrations/*budget*.sql"
      - "services/core-api/app/modules/budget/**"
      - "services/core-api/**/*budget*.py"
      - "services/core-api/alembic/versions/*budget*.py"
      - "src/**/*budget*"
      - "src/**/Budget/**"
      - "config/**/*budget*"
      - "scripts/**/*budget*"
      - "config/eay_master_roadmap_60.json"
      - ".github/workflows/eay-master-roadmap-28-budget-planning-engine.yml"
"""

DOCKOS_PR_OLD = """  pull_request:
  workflow_dispatch:
"""
DOCKOS_PR_NEW = """  pull_request:
    paths:
      - "backend/app/modules/workforce/**"
      - "backend/app/modules/recruitment/**"
      - "backend/app/modules/dockos/**"
      - "backend/app/modules/inventory/**"
      - "backend/app/test_security.py"
      - "backend/migrations/*workforce*.sql"
      - "backend/migrations/*dockos*.sql"
      - "backend/migrations/*inventory*.sql"
      - "backend/migrations/*recruit*.sql"
      - "backend/scripts/setup_workforce_postgres_ci.py"
      - "backend/scripts/workforce_postgres_load_ci.py"
      - "backend/scripts/verify_workforce_restore_ci.py"
      - "backend/requirements.txt"
      - "src/**/*workforce*"
      - "src/**/Workforce/**"
      - "src/**/*dockos*"
      - "src/**/DockOS/**"
      - "src/**/*hiring*"
      - "src/**/Hiring/**"
      - "src/**/*recruit*"
      - "src/**/Recruitment/**"
      - "src/**/*inventory*"
      - "src/**/Inventory/**"
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
      - "services/core-api/app/budget_main.py"
      - "services/core-api/tests/test_ai_*.py"
      - "services/core-api/tests/test_security_foundation.py"
      - "services/core-api/tests/test_sql_access_boundary.py"
      - "services/core-api/alembic/versions/*ai*.py"
      - "services/core-api/alembic/versions/*jarvis*.py"
      - "services/core-api/alembic/versions/*orders*.py"
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
    # Historical gates remain callable on the product-completion line and via
    # workflow_dispatch, but stop multiplying every category-leadership PR.
    for name in LEGACY:
        text = read(name)
        text = replace_exact(
            text, LEGACY_PR_OLD, LEGACY_PR_NEW, count=1, label=f"{name} legacy PR scope"
        )
        if name in EXACT:
            item = name.removeprefix("eay-roadmap-").removesuffix("-exact-head.yml")
            old_group = (
                f"group: eay-roadmap-{item}-exact-"
                "${{ github.event.pull_request.head.sha || github.sha }}"
            )
            new_group = (
                "group: ${{ github.workflow }}-"
                "${{ github.event.pull_request.number || github.ref }}"
            )
            text = replace_exact(
                text, old_group, new_group, count=1, label=f"{name} concurrency"
            )
        write(name, text)

    # PR = domain delta. Canonical category push remains intentionally broad and
    # still proves cumulative composition after a workstream is integrated.
    for name in PLANOGRAM:
        text = read(name)
        text = replace_exact(
            text, PLANOGRAM_PR_OLD, PLANOGRAM_PR_NEW, count=1, label=f"{name} PR paths"
        )
        if name != "eay-master-roadmap-24-27-cumulative-exact-head.yml":
            text = add_concurrency_before_jobs(text, label=f"{name} concurrency")
        write(name, text)

    text = read(BUDGET)
    text = replace_exact(
        text, BUDGET_PR_OLD, BUDGET_PR_NEW, count=1, label=f"{BUDGET} PR paths"
    )
    write(BUDGET, text)

    text = read(DOCKOS)
    text = replace_exact(
        text, DOCKOS_PR_OLD, DOCKOS_PR_NEW, count=1, label=f"{DOCKOS} PR paths"
    )
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

    stable = (
        "group: ${{ github.workflow }}-"
        "${{ github.event.pull_request.number || github.ref }}"
    )
    for name in EXACT:
        text = read(name)
        concurrency_block = text.split("env:", 1)[0]
        if "head.sha || github.sha" in concurrency_block:
            failures.append(f"{name}: SHA-keyed PR concurrency still present")
        if stable not in text:
            failures.append(f"{name}: stable PR concurrency missing")

    for name in PLANOGRAM:
        text = read(name)
        pr_block = text.split("  pull_request:", 1)[1].split("\n\n", 1)[0]
        if "    paths:" not in pr_block:
            failures.append(f"{name}: PR path admission missing")
        if '"services/core-api/alembic/**"' in pr_block:
            failures.append(f"{name}: broad migration path would reintroduce fan-out")

    budget = read(BUDGET)
    budget_pr = budget.split("  pull_request:", 1)[1].split("  workflow_dispatch:", 1)[0]
    if "    paths:" not in budget_pr:
        failures.append(f"{BUDGET}: PR path admission missing")

    dockos = read(DOCKOS)
    if "  pull_request:\n    paths:" not in dockos:
        failures.append(f"{DOCKOS}: global pull_request fan-out still present")
    if '- "backend/**"' in dockos:
        failures.append(f"{DOCKOS}: backend-wide PR admission is still too broad")
    if stable not in dockos:
        failures.append(f"{DOCKOS}: stable concurrency missing")

    jarvis = read(JARVIS)
    if '- "services/core-api/**"' in jarvis:
        failures.append(f"{JARVIS}: broad Core API path still present")
    if '- "services/core-api/alembic/**"' in jarvis:
        failures.append(f"{JARVIS}: all-migration fan-out still present")
    if jarvis.count('- "services/core-api/app/core/ai_*.py"') != 2:
        failures.append(f"{JARVIS}: narrowed Orders/Jarvis paths not present on push and PR")

    # Release Authority stays separate and must not be rewritten by this policy.
    release_authority = read("eay-master-roadmap-56-60-release-leadership.yml")
    if "paths:" not in release_authority.split("permissions:", 1)[0]:
        failures.append("release authority lost its reviewed path-scoped admission")
    if "group: eay-master-56-60-${{ github.ref }}" not in release_authority:
        failures.append("release authority concurrency changed unexpectedly")

    if failures:
        raise SystemExit("CI admission-control verification failed:\n- " + "\n- ".join(failures))

    print("CI_ADMISSION_CONTROL=PASS")
    print("legacy_category_pr_fanout=false")
    print("superseded_pr_sha_concurrency=false")
    print("planogram_pr_admission=scoped")
    print("budget_pr_admission=scoped")
    print("dockos_global_pr_fanout=false")
    print("jarvis_core_api_fanout=false")
    print("canonical_push_cumulative_regression=preserved")
    print("release_authority_policy=preserved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        apply()
    check()


if __name__ == "__main__":
    main()
