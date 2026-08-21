from __future__ import annotations

import json
import re
from pathlib import Path

ROADMAP = Path("config/eay_master_roadmap_60.json")
ALLOWED_REPOSITORY = {"UNVERIFIED", "PARTIAL", "COMPLETE", "REGRESSED"}
ALLOWED_EXTERNAL = {"NOT_REQUIRED", "REQUIRED", "PARTIAL", "COMPLETE"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    data = json.loads(ROADMAP.read_text(encoding="utf-8"))
    if data.get("authority") != "EAY_MASTER_ROADMAP_60":
        fail("master roadmap authority marker missing")
    items = data.get("items")
    if not isinstance(items, list) or len(items) != 60:
        fail("master roadmap must contain exactly 60 items")
    ids = [item.get("id") for item in items]
    if ids != list(range(1, 61)):
        fail("master roadmap IDs must be exact ordered range 1..60")

    for item in items:
        item_id = item["id"]
        title = item.get("title")
        repo_status = item.get("repository_status")
        external_status = item.get("external_status")
        evidence = item.get("evidence")
        if not isinstance(title, str) or not title.strip():
            fail(f"item {item_id}: title missing")
        if repo_status not in ALLOWED_REPOSITORY:
            fail(f"item {item_id}: invalid repository status {repo_status!r}")
        if external_status not in ALLOWED_EXTERNAL:
            fail(f"item {item_id}: invalid external status {external_status!r}")
        if not isinstance(evidence, list):
            fail(f"item {item_id}: evidence must be a list")

        if repo_status == "COMPLETE":
            if not evidence:
                fail(f"item {item_id}: COMPLETE requires evidence")
            exact_head = [entry for entry in evidence if entry.get("kind") == "exact_head_ci"]
            if not exact_head:
                fail(f"item {item_id}: COMPLETE requires exact_head_ci evidence")
            for entry in exact_head:
                if not SHA_RE.fullmatch(str(entry.get("sha", ""))):
                    fail(f"item {item_id}: exact_head_ci evidence requires immutable SHA")
                if entry.get("conclusion") != "success":
                    fail(f"item {item_id}: exact_head_ci evidence must be success")

        if external_status == "COMPLETE":
            external = [entry for entry in evidence if entry.get("kind") == "external_acceptance"]
            if not external:
                fail(f"item {item_id}: external COMPLETE requires external_acceptance evidence")
            if not all(entry.get("verified") is True for entry in external):
                fail(f"item {item_id}: external acceptance must be explicitly verified")

        if repo_status == "REGRESSED" and external_status == "COMPLETE":
            fail(f"item {item_id}: regressed repository state cannot claim completed production evidence")

    print("EAY canonical 60-item master roadmap authority: PASS")


if __name__ == "__main__":
    main()
