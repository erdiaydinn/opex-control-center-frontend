#!/usr/bin/env python3
"""Read-only verifier for EAY GitHub Actions admission policy.

Workstream PRs run scoped delta gates. The rolling category PR back to
product-completion retains the 1-10..1-14 cumulative bridge required by later
exact-head gates. Archived copies remain version-controlled for audit.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "docs" / "ci" / "historical-workflows"

ROLLING_BRIDGE = (
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


def read(name: str) -> str:
    path = WF / name
    if not path.is_file():
        raise AssertionError(f"required active workflow missing: {name}")
    return path.read_text(encoding="utf-8")


def header(source: str) -> str:
    return source.split("jobs:", 1)[0]


def pull_request_block(source: str) -> str:
    head = header(source)
    if "pull_request:" not in head:
        raise AssertionError("pull_request admission missing")
    block = head.split("pull_request:", 1)[1]
    for marker in ("\n  push:", "\n  workflow_dispatch:", "\npermissions:", "\nconcurrency:"):
        if marker in block:
            block = block.split(marker, 1)[0]
    return block


def stable_non_sha(name: str, source: str) -> None:
    head = header(source)
    if "concurrency:" not in head:
        raise AssertionError(f"{name}: concurrency missing")
    if "cancel-in-progress: true" not in head:
        raise AssertionError(f"{name}: superseded-run cancellation missing")
    concurrency = head.split("concurrency:", 1)[1]
    if "head.sha" in concurrency or "github.sha" in concurrency:
        raise AssertionError(f"{name}: concurrency still keyed by immutable commit SHA")
    if "github.ref" not in concurrency and "github.event.pull_request.number" not in concurrency:
        raise AssertionError(f"{name}: concurrency lacks stable PR/ref identity")


def require_pr_paths(name: str, required: tuple[str, ...]) -> None:
    source = read(name)
    block = pull_request_block(source)
    if "paths:" not in block:
        raise AssertionError(f"{name}: PR path scope missing")
    for fragment in required:
        if fragment not in block:
            raise AssertionError(f"{name}: expected PR path missing: {fragment}")
    stable_non_sha(name, source)


def main() -> None:
    failures: list[str] = []

    def check(fn) -> None:
        try:
            fn()
        except AssertionError as exc:
            failures.append(str(exc))

    # These gates are not general workstream PR gates. They exist only to
    # re-prove the rolling category PR (#94) against product-completion so
    # 1-15+ can require the previous exact-head result without deadlocking.
    for name in ROLLING_BRIDGE:
        def rolling_check(name=name) -> None:
            source = read(name)
            block = pull_request_block(source)
            if "product/eay-product-completion-v1" not in block:
                raise AssertionError(f"{name}: rolling product-completion PR admission missing")
            if "product/eay-category-leadership-v1" in block:
                raise AssertionError(f"{name}: category-targeted workstream PR admission must stay disabled")
            if not (ARCHIVE / name).is_file():
                raise AssertionError(f"{name}: audit archive missing")
            stable_non_sha(name, source)
        check(rolling_check)

    for helper in (
        ROOT / "scripts/ci/apply_inventory_admission_control.py",
        ROOT / "scripts/ci/migrate_legacy_exact_head_headers.py",
    ):
        if helper.exists():
            failures.append(f"temporary mutation helper still present: {helper.relative_to(ROOT)}")

    def dockos_check() -> None:
        source = read("dockos-full-stack.yml")
        block = pull_request_block(source)
        if "paths:" not in block:
            raise AssertionError("DockOS still has global pull_request admission")
        for forbidden in (
            '"backend/app/modules/inventory/**"',
            '"backend/migrations/*inventory*.sql"',
            '"src/**/*inventory*"',
            '"src/**/Inventory/**"',
            '"android-inventory/**"',
        ):
            if forbidden in block:
                raise AssertionError(f"DockOS still consumes Inventory PR admission: {forbidden}")
        stable_non_sha("dockos-full-stack.yml", source)
    check(dockos_check)

    def inventory_check() -> None:
        source = read("eay-inventory-production.yml")
        block = pull_request_block(source)
        if "product/eay-category-leadership-v1" not in block:
            raise AssertionError("Inventory Production Gate missing category PR admission")
        if '"backend/app/modules/inventory/**"' not in block:
            raise AssertionError("Inventory Production Gate missing inventory path scope")
        if "find backend/app -type f -name 'test_*.py'" in source:
            raise AssertionError("Inventory gate still executes every backend domain test")
        if "backend.app.test_security" in source:
            raise AssertionError("Inventory gate still owns generic identity/security tests")
        stable_non_sha("eay-inventory-production.yml", source)
        android = read("opex-inventory-android.yml")
        if '"android-inventory/**"' not in pull_request_block(android):
            raise AssertionError("Inventory Android gate lost Android path scope")
        stable_non_sha("opex-inventory-android.yml", android)
    check(inventory_check)

    for name in PLANOGRAM:
        check(lambda name=name: require_pr_paths(name, ('"apps/planai/**"',)))
    check(lambda: require_pr_paths(
        "eay-master-roadmap-28-budget-planning-engine.yml",
        ('"backend/app/modules/budget/**"',),
    ))

    def jarvis_check() -> None:
        source = read("jarvis-convergence-ci.yml")
        block = pull_request_block(source)
        if "paths:" not in block:
            raise AssertionError("Jarvis Orders V2 PR path scope missing")
        if '- "services/core-api/**"' in block:
            raise AssertionError("Jarvis Orders V2 still admits the whole Core API")
        if '"services/core-api/app/core/ai_*.py"' not in block:
            raise AssertionError("Jarvis governed AI Core API path missing")
        stable_non_sha("jarvis-convergence-ci.yml", source)
    check(jarvis_check)

    release_path = WF / "eay-master-roadmap-56-60-release-leadership.yml"
    if release_path.exists():
        release = release_path.read_text(encoding="utf-8")
        if "EAY Master Roadmap 56-60 - Release Authority" not in release:
            failures.append("unexpected Master 56-60 release authority identity")
        print("release_authority_phase=composed_and_preserved")
    else:
        print("release_authority_phase=separate_workstream")

    guard = read("ci-admission-guard.yml")
    if "contents: read" not in guard:
        failures.append("CI Admission Guard must remain read-only")
    stable_non_sha("ci-admission-guard.yml", guard)

    if failures:
        raise SystemExit("CI admission policy verification failed:\n- " + "\n- ".join(failures))

    print("CI_ADMISSION_POLICY=PASS")
    print("rolling_1_10_1_14=product_completion_only")
    print("category_targeted_workstream_legacy_fanout=false")
    print("domain_heavy_pr_admission=scoped")
    print("superseded_pr_runs=stable_non_sha_concurrency")
    print("dockos_inventory_fanout=false")
    print("jarvis_core_api_fanout=false")
    print("canonical_cumulative_chain=preserved")


if __name__ == "__main__":
    main()
