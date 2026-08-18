#!/usr/bin/env python3
"""Verify EAY GitHub Actions admission policy.

The policy separates workstream PR checks from cumulative canonical/release
acceptance. Historical Roadmap 1-10..1-14 gates remain versioned for audit but
must not stay active under .github/workflows. Heavy domain gates must be
path-scoped on PRs and use non-SHA stable concurrency so superseded commits can
cancel.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "docs" / "ci" / "historical-workflows"
CATEGORY = "product/eay-category-leadership-v1"
RELEASE_AUTHORITY = "eay-master-roadmap-56-60-release-leadership.yml"

HISTORICAL = (
    "eay-roadmap-1-10-acceptance.yml",
    "eay-roadmap-1-10-exact-head.yml",
    "eay-roadmap-1-11-exact-head.yml",
    "eay-roadmap-1-12-exact-head.yml",
    "eay-roadmap-1-13-exact-head.yml",
    "eay-roadmap-1-14-exact-head.yml",
)

PLANOGRAM = (
    "eay-master-roadmap-24-planogram-physical-truth.yml",
    "eay-master-roadmap-25-planogram-optimizer.yml",
    "eay-master-roadmap-26-planogram-execution-compliance.yml",
    "eay-master-roadmap-24-27-cumulative-exact-head.yml",
)


def text(name: str) -> str:
    path = WF / name
    if not path.is_file():
        raise AssertionError(f"required active workflow missing: {name}")
    return path.read_text(encoding="utf-8")


def header(source: str) -> str:
    return source.split("jobs:", 1)[0]


def require_stable_concurrency(name: str, head: str) -> None:
    assert "concurrency:" in head, f"{name}: concurrency block missing"
    assert "cancel-in-progress: true" in head, f"{name}: superseded-run cancellation missing"
    assert "head.sha" not in head, f"{name}: PR head SHA used as concurrency identity"
    assert "github.sha" not in head, f"{name}: commit SHA used as concurrency identity"
    assert (
        "github.event.pull_request.number" in head or "github.ref" in head
    ), f"{name}: concurrency is not bound to a stable PR/ref identity"


def pull_request_block(head: str) -> str:
    assert "pull_request:" in head, "pull_request admission missing"
    pr = head.split("pull_request:", 1)[1]
    for boundary in ("workflow_dispatch:", "permissions:", "concurrency:"):
        if boundary in pr:
            pr = pr.split(boundary, 1)[0]
    if "\n  push:" in pr:
        pr = pr.split("\n  push:", 1)[0]
    return pr


def require_pr_paths(name: str, *, required_fragment: str | None = None) -> None:
    source = text(name)
    head = header(source)
    pr = pull_request_block(head)
    assert "paths:" in pr, f"{name}: PR path scope missing"
    require_stable_concurrency(name, head)
    if required_fragment:
        assert required_fragment in pr, f"{name}: expected scoped path missing: {required_fragment}"


def check_historical() -> None:
    for name in HISTORICAL:
        assert not (WF / name).exists(), f"historical workflow still active: {name}"
        assert (ARCHIVE / name).is_file(), f"historical workflow archive missing: {name}"
    for name in ("ci-admission-finalize.yml", "ci-exact-head-base-migration.yml"):
        assert not (WF / name).exists(), f"temporary migration workflow still active: {name}"
    print("CI_ADMISSION_HISTORICAL=PASS")


def check_inventory_dockos() -> None:
    dockos = text("dockos-full-stack.yml")
    require_pr_paths("dockos-full-stack.yml", required_fragment="backend/app/modules/dockos/**")
    dockos_pr = pull_request_block(header(dockos))
    assert "backend/app/modules/inventory/**" not in dockos_pr, "DockOS PR scope includes Inventory"
    assert "android-inventory/**" not in dockos_pr, "DockOS PR scope includes Android Inventory"

    inventory = text("eay-inventory-production.yml")
    inventory_head = header(inventory)
    inventory_pr = pull_request_block(inventory_head)
    assert CATEGORY in inventory_pr, "Inventory production gate missing category PR admission"
    assert "paths:" in inventory_pr, "Inventory production PR path scope missing"
    require_stable_concurrency("eay-inventory-production.yml", inventory_head)
    require_stable_concurrency("opex-inventory-android.yml", header(text("opex-inventory-android.yml")))
    print("CI_ADMISSION_INVENTORY_DOCKOS=PASS")


def check_planogram_budget() -> None:
    for name in PLANOGRAM:
        require_pr_paths(name, required_fragment="planogram")
    require_pr_paths("eay-master-roadmap-28-budget-planning-engine.yml", required_fragment="budget")
    print("CI_ADMISSION_PLANOGRAM_BUDGET=PASS")


def check_jarvis_release() -> None:
    jarvis = text("jarvis-convergence-ci.yml")
    jarvis_head = header(jarvis)
    jarvis_pr = pull_request_block(jarvis_head)
    assert "paths:" in jarvis_pr, "Jarvis PR path scope missing"
    assert '"services/core-api/**"' not in jarvis_pr, "Jarvis gate still consumes the whole Core API tree"
    require_stable_concurrency("jarvis-convergence-ci.yml", jarvis_head)

    # Master 56-60 Release Authority currently lives on its own workstream PR
    # until composed into category canonical. Admission control must not create
    # or replace a parallel authority. Once present, verify its canonical name.
    release = WF / RELEASE_AUTHORITY
    if release.is_file():
        release_source = release.read_text(encoding="utf-8")
        assert "EAY Master Roadmap 56-60 - Release Authority" in release_source, (
            "unexpected Master 56-60 release workflow identity"
        )
        print("CI_ADMISSION_RELEASE_AUTHORITY=PRESENT_PRESERVED")
    else:
        print("CI_ADMISSION_RELEASE_AUTHORITY=SEPARATE_WORKSTREAM")
    print("CI_ADMISSION_JARVIS_RELEASE=PASS")


SECTIONS = {
    "historical": check_historical,
    "inventory-dockos": check_inventory_dockos,
    "planogram-budget": check_planogram_budget,
    "jarvis-release": check_jarvis_release,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=tuple(SECTIONS))
    args = parser.parse_args()
    if args.section:
        SECTIONS[args.section]()
        return
    for check in SECTIONS.values():
        check()
    print("EAY_CI_ADMISSION_POLICY=PASS")
    print("historical_1_10_1_14=archived_inert")
    print("domain_pr_gates=path_scoped")
    print("superseded_pr_runs=stable_non_sha_concurrency")
    print("release_authority=preserved_or_separate_workstream")


if __name__ == "__main__":
    main()
