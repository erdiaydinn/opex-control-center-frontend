from __future__ import annotations

from pathlib import Path

TARGETS = [
    Path(f".github/workflows/eay-roadmap-1-{item}-exact-head.yml")
    for item in range(11, 15)
]

OLD_BRANCHES = """  pull_request:
    branches:
      - product/eay-product-completion-v1
"""
NEW_BRANCHES = """  pull_request:
    branches:
      - product/eay-product-completion-v1
      - product/eay-category-leadership-v1
"""

OLD_MIGRATION = """      - name: Migrate exact head
        working-directory: services/core-api
        run: |
          alembic upgrade head
          alembic current | grep -q '0029_field_template_lifecycle_column_grant'
"""
NEW_MIGRATION = """      - name: Migrate exact head and preserve item 10 lineage
        working-directory: services/core-api
        shell: bash
        run: |
          set -euo pipefail
          mapfile -t heads < <(alembic heads | awk '/\\(head\\)/ {print $1}')
          printf 'ALEMBIC_HEAD=%s\\n' "${heads[@]}"
          test "${#heads[@]}" -eq 1
          alembic history > /tmp/eay-alembic-history.txt
          grep -q '0029_field_template_lifecycle_column_grant' /tmp/eay-alembic-history.txt
          alembic upgrade head
          current="$(alembic current | awk '/\\(head\\)/ {print $1}')"
          test "$current" = "${heads[0]}"
"""


def replace_once(text: str, old: str, new: str, *, label: str, path: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    changed: list[str] = []
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        if "product/eay-category-leadership-v1" not in text.split("workflow_dispatch:", 1)[0]:
            text = replace_once(
                text,
                OLD_BRANCHES,
                NEW_BRANCHES,
                label="pull_request branch block",
                path=path,
            )
        if "alembic current | grep -q '0029_field_template_lifecycle_column_grant'" in text:
            text = replace_once(
                text,
                OLD_MIGRATION,
                NEW_MIGRATION,
                label="stale migration current-head block",
                path=path,
            )
        else:
            required = (
                "test \"${#heads[@]}\" -eq 1",
                "grep -q '0029_field_template_lifecycle_column_grant' /tmp/eay-alembic-history.txt",
                'test "$current" = "${heads[0]}"',
            )
            if not all(item in text for item in required):
                raise RuntimeError(f"{path}: neither stale nor repaired migration block found")
        path.write_text(text, encoding="utf-8")
        changed.append(str(path))

    print("ROADMAP_LEGACY_MIGRATION_GATE_REPAIR=PASS")
    for path in changed:
        print(f"REPAIRED={path}")


if __name__ == "__main__":
    main()
