#!/usr/bin/env python3
"""Generate a CycloneDX build-phase dependency closure from installed metadata.

This is deliberately build-environment evidence. It records the versions that are
actually installed for the requested root distribution and follows installed
Requires-Dist metadata conservatively. Optional/marker dependencies that are
present may be over-approximated; production runtime/deployment attestation and
reachability are explicitly out of scope.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import re
from pathlib import Path
from typing import Any

from validate_prebuild_evidence_contract import validate_document

SPEC_VERSION = "1.7"
NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def requirement_name(value: str) -> str | None:
    match = NAME_PATTERN.match(value)
    return normalize_name(match.group(1)) if match else None


def installed_distributions() -> dict[str, metadata.Distribution]:
    result: dict[str, metadata.Distribution] = {}
    for distribution in metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        version = distribution.version
        if not raw_name or not version:
            continue
        result[normalize_name(raw_name)] = distribution
    return result


def dependency_edges(
    installed: dict[str, metadata.Distribution],
) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {}
    for name, distribution in installed.items():
        dependencies: set[str] = set()
        for requirement in distribution.requires or ():
            child = requirement_name(requirement)
            if child and child in installed:
                dependencies.add(child)
        edges[name] = dependencies
    return edges


def reachable_names(root: str, edges: dict[str, set[str]]) -> set[str]:
    pending = [root]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(edges.get(current, ()))
    return seen


def purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name}@{version}"


def build_bom(root_name: str) -> dict[str, Any]:
    installed = installed_distributions()
    root = normalize_name(root_name)
    if root not in installed:
        raise ValueError(f"root Python distribution is not installed: {root_name}")

    edges = dependency_edges(installed)
    reachable = reachable_names(root, edges)
    components: list[dict[str, Any]] = []

    for name in sorted(reachable):
        distribution = installed[name]
        version = distribution.version
        components.append(
            {
                "type": "application" if name == root else "library",
                "bom-ref": purl(name, version),
                "name": name,
                "version": version,
                "purl": purl(name, version),
                "scope": "required",
                "properties": [
                    {
                        "name": "eay:resolution-state",
                        "value": "installed-build-environment",
                    }
                ],
            }
        )

    dependency_graph = []
    for name in sorted(reachable):
        distribution = installed[name]
        direct = sorted(child for child in edges.get(name, ()) if child in reachable)
        dependency_graph.append(
            {
                "ref": purl(name, distribution.version),
                "dependsOn": [purl(child, installed[child].version) for child in direct],
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "lifecycles": [{"phase": "build"}],
            "component": {
                "type": "application",
                "name": root,
                "version": installed[root].version,
                "purl": purl(root, installed[root].version),
            },
            "properties": [
                {
                    "name": "eay:truth-boundary",
                    "value": (
                        "resolved installed build-environment dependency closure; "
                        "not production runtime/deployment attestation or reachability proof"
                    ),
                },
                {
                    "name": "eay:graph-semantics",
                    "value": (
                        "installed Requires-Dist closure; optional and environment-marker "
                        "dependencies may be conservatively over-approximated when installed"
                    ),
                },
            ],
        },
        "components": components,
        "dependencies": dependency_graph,
    }


def validate_bom(bom: dict[str, Any]) -> None:
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != SPEC_VERSION:
        raise ValueError("unexpected CycloneDX document identity")
    if bom.get("metadata", {}).get("lifecycles") != [{"phase": "build"}]:
        raise ValueError("Python environment SBOM must remain build-phase evidence")

    components = bom.get("components") or []
    refs = {component.get("bom-ref") for component in components}
    if None in refs or len(refs) != len(components):
        raise ValueError("Python build SBOM component refs must be unique and non-empty")
    if any(not component.get("version") for component in components):
        raise ValueError("Python build SBOM must contain actual installed versions")

    graph = bom.get("dependencies") or []
    graph_refs = {item.get("ref") for item in graph}
    if graph_refs != refs:
        raise ValueError("Python build dependency graph must cover every component")
    for item in graph:
        if any(child not in refs for child in item.get("dependsOn", [])):
            raise ValueError("Python build dependency graph contains an unknown component ref")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bom = build_bom(args.root)
    validate_bom(bom)
    validate_document(bom, source=args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bom, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    edge_count = sum(len(item["dependsOn"]) for item in bom["dependencies"])
    print(
        "Python CycloneDX build dependency closure: PASS "
        f"(root={normalize_name(args.root)}, components={len(bom['components'])}, "
        f"edges={edge_count}, production_runtime_proof=false)"
    )


if __name__ == "__main__":
    main()
