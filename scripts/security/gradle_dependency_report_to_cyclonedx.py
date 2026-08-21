#!/usr/bin/env python3
"""Convert a Gradle dependency report into a truthful pre-build CycloneDX BOM.

Input must be the resolved `:app:dependencies --configuration releaseRuntimeClasspath`
report produced by Gradle in CI. The converter records only coordinates that are
actually present in that resolved report and never claims runtime/deployment
attestation or reachability.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from validate_prebuild_evidence_contract import validate_document

SPEC_VERSION = "1.7"
COORDINATE = re.compile(
    r"(?:---|\\---|\\+---|\+---)\s+"
    r"(?P<group>[A-Za-z0-9_.-]+):"
    r"(?P<name>[A-Za-z0-9_.-]+):"
    r"(?P<requested>[^\s()]+)"
    r"(?:\s+->\s+(?P<resolved>[^\s()]+))?"
)


def final_version(requested: str, resolved: str | None) -> str:
    if not resolved:
        return requested
    if resolved.count(":") >= 2:
        return resolved.rsplit(":", maxsplit=1)[-1]
    return resolved


def parse_components(text: str) -> list[dict[str, Any]]:
    versions: dict[tuple[str, str], set[str]] = {}
    for raw_line in text.splitlines():
        match = COORDINATE.search(raw_line)
        if match is None:
            continue
        group = match.group("group")
        name = match.group("name")
        version = final_version(match.group("requested"), match.group("resolved"))
        if not version or version in {"FAILED", "(*)", "(c)"}:
            continue
        versions.setdefault((group, name), set()).add(version)

    if not versions:
        raise ValueError("Gradle report did not contain resolved release runtime coordinates")

    conflicting = {
        f"{group}:{name}": sorted(found)
        for (group, name), found in versions.items()
        if len(found) != 1
    }
    if conflicting:
        raise ValueError(
            "Gradle release runtime report contains conflicting resolved versions: "
            + json.dumps(conflicting, sort_keys=True)
        )

    components: list[dict[str, Any]] = []
    for (group, name), found in sorted(versions.items()):
        version = next(iter(found))
        components.append(
            {
                "type": "library",
                "bom-ref": f"pkg:maven/{group}/{name}@{version}",
                "group": group,
                "name": name,
                "version": version,
                "purl": f"pkg:maven/{group}/{name}@{version}",
                "scope": "required",
                "properties": [
                    {
                        "name": "eay:source-configuration",
                        "value": "releaseRuntimeClasspath",
                    },
                    {
                        "name": "eay:resolution-state",
                        "value": "gradle-build-resolved",
                    },
                ],
            }
        )
    return components


def build_bom(components: list[dict[str, Any]]) -> dict[str, Any]:
    refs = [component["bom-ref"] for component in components]
    if len(refs) != len(set(refs)):
        raise ValueError("Android CycloneDX bom-ref values must be unique")

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "lifecycles": [{"phase": "pre-build"}],
            "component": {
                "type": "application",
                "name": "EAY Inventory Android",
                "version": "30.0.1-p0",
            },
            "properties": [
                {
                    "name": "eay:truth-boundary",
                    "value": (
                        "Gradle-resolved releaseRuntimeClasspath build evidence; "
                        "not production runtime/deployment attestation or reachability proof"
                    ),
                },
                {
                    "name": "eay:source-command",
                    "value": "gradle :app:dependencies --configuration releaseRuntimeClasspath",
                },
            ],
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = args.input.read_text(encoding="utf-8", errors="strict")
    components = parse_components(report)
    bom = build_bom(components)
    validate_document(bom, source=args.output)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bom, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "Android CycloneDX pre-build runtime graph: PASS "
        f"(resolved_components={len(components)}, production_runtime_proof=false)"
    )


if __name__ == "__main__":
    main()
