#!/usr/bin/env python3
"""Verify EAY GitHub Actions admission policy.

The policy separates workstream PR checks from cumulative canonical/release
acceptance. Historical Roadmap 1-10..1-14 gates remain versioned for audit but
must not stay active under .github/workflows. Heavy domain gates must be
path-scoped on PRs and use stable concurrency so superseded commits can cancel.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "docs" / "ci" / "historical-workflows"
STABLE = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
CATEGORY = "product/eay-category-leadership-v1"

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


def require_pr_paths(name: str, *, required_fragment: str | None = None) -> None:
    source = text(name)
    head = header(source)
    assert "pull_request:" in head, f"{name}: pull_request admission missing"
    pr = head.split("pull_request:", 1)[1]
    if "push:" in pr:
        pr = pr.split("push:", 1)[0]
    if "workflow_dispatch:" in pr:
        pr = pr.split("workflow_dispatch:", 1)[0]
    assert "paths:" in pr, f"{name}: PR path scope missing"
    assert STABLE in head, f"{name}: stable concurrency missing"
    if required_fragment:
        assert required_fragment in pr, f"{name}: expected scoped path missing: {required_fragment}"


def main() -> None:
    # Historical acceptance evidence stays available for audit but is inert.
    for name in HISTORICAL:
        assert not (WF / name).exists(), f"historical workflow still active: {name}"
        assert (ARCHIVE / name).is_file(), f"historical workflow archive missing: {name}"

    # Temporary write-capable migration workflows must never survive the fix.
    for name in ("ci-admission-finalize.yml", "ci-exact-head-base-migration.yml"):
        assert not (WF / name).exists(), f"temporary migration workflow still active: {name}"

    # DockOS is no longer a global PR gate and does not impersonate Inventory CI.
    dockos = text("dockos-full-stack.yml")
    require_pr_paths("dockos-full-stack.yml", required_fragment="backend/app/modules/dockos/**")
    dockos_pr = header(dockos).split("pull_request:", 1)[1].split("workflow_dispatch:", 1)[0]
    assert "backend/app/modules/inventory/**" not in dockos_pr, "DockOS PR scope includes Inventory"
    assert "android-inventory/**" not in dockos_pr, "DockOS PR scope includes Android Inventory"

    # Inventory changes have their own production-shaped authority gates.
    inventory = text("eay-inventory-production.yml")
    inventory_head = header(inventory)
    assert CATEGORY in inventory_head, "Inventory production gate missing category PR admission"
    assert "paths:" in inventory_head, "Inventory production PR path scope missing"
    assert STABLE in inventory_head, "Inventory production stable concurrency missing"
    android = text("opex-inventory-android.yml")
    assert STABLE in header(android), "Inventory Android stable concurrency missing"

    # Planogram and Budget workstream PRs run only their relevant delta gates.
    for name in PLANOGRAM:
        require_pr_paths(name, required_fragment="planogram")
    require_pr_paths("eay-master-roadmap-28-budget-planning-engine.yml", required_fragment="budget")

    # Jarvis Orders V2 may use focused Core paths, never the whole Core API tree.
    jarvis = text("jarvis-convergence-ci.yml")
    jarvis_head = header(jarvis)
    assert "pull_request:" in jarvis_head and "paths:" in jarvis_head, "Jarvis PR path scope missing"
    assert '"services/core-api/**"' not in jarvis_head, "Jarvis gate still consumes the whole Core API tree"
    assert STABLE in jarvis_head, "Jarvis stable concurrency missing"

    # Final release authority remains active and is not replaced by this guard.
    release = WF / "eay-master-roadmap-56-60-release-leadership.yml"
    assert release.is_file(), "Master 56-60 Release Authority workflow missing"

    print("EAY_CI_ADMISSION_POLICY=PASS")
    print("historical_1_10_1_14=archived_inert")
    print("domain_pr_gates=path_scoped")
    print("superseded_pr_runs=stable_concurrency")
    print("release_authority=preserved")


if __name__ == "__main__":
    main()
