#!/usr/bin/env python3
"""Generate a truthful pre-build CycloneDX inventory without inventing resolution.

The root npm lockfile contributes resolved package versions. Python pyproject files
contribute declared direct requirements only; those entries deliberately omit a
resolved version and retain the original requirement as evidence. This is a
pre-build inventory, not a production/runtime SBOM or reachability proof.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import quote

from validate_prebuild_evidence_contract import validate_document

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_LOCK = REPO_ROOT / "package-lock.json"
PYTHON_MANIFESTS = (
    REPO_ROOT / "services/core-api/pyproject.toml",
    REPO_ROOT / "services/identity-gateway/pyproject.toml",
)
SPEC_VERSION = "1.7"
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def property_item(name: str, value: str) -> dict[str, str]:
    return {"name": name, "value": value}


def npm_purl(name: str, version: str) -> str:
    safe = ".-_~"
    encoded_version = quote(version, safe=safe)
    if name.startswith("@") and "/" in name:
        namespace, package_name = name.split("/", maxsplit=1)
        return (
            "pkg:npm/"
            f"{quote(namespace, safe=safe)}/{quote(package_name, safe=safe)}"
            f"@{encoded_version}"
        )
    return f"pkg:npm/{quote(name, safe=safe)}@{encoded_version}"


def npm_components() -> list[dict[str, Any]]:
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("package-lock.json must expose the npm packages map")

    components: list[dict[str, Any]] = []
    for package_path, entry in packages.items():
        if not package_path or "node_modules/" not in package_path:
            continue
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if not isinstance(version, str) or not version:
            raise ValueError(f"npm package lacks resolved version: {package_path}")

        name = package_path.rsplit("node_modules/", maxsplit=1)[-1]
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": f"npm-path:{package_path}@{version}",
            "name": name,
            "version": version,
            "purl": npm_purl(name, version),
            "scope": "excluded" if entry.get("dev") is True else "required",
            "properties": [
                property_item("eay:ecosystem", "npm"),
                property_item("eay:source-manifest", "package-lock.json"),
                property_item("eay:package-path", package_path),
                property_item("eay:resolution-state", "lockfile-resolved"),
            ],
        }
        integrity = entry.get("integrity")
        if isinstance(integrity, str) and integrity:
            component["properties"].append(property_item("eay:npm-integrity", integrity))
        resolved = entry.get("resolved")
        if isinstance(resolved, str) and resolved:
            component["properties"].append(property_item("eay:npm-resolved", resolved))
        components.append(component)

    if not components:
        raise ValueError("no resolved npm components were discovered")
    return components


def python_components() -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for manifest in PYTHON_MANIFESTS:
        document = tomllib.loads(manifest.read_text(encoding="utf-8"))
        project = document.get("project", {})
        project_name = str(project.get("name") or manifest.parent.name)

        dependency_groups: list[tuple[str, list[str], str]] = [
            ("runtime", list(project.get("dependencies") or []), "required"),
        ]
        optional = project.get("optional-dependencies") or {}
        for group_name, requirements in sorted(optional.items()):
            scope = "excluded" if group_name == "dev" else "optional"
            dependency_groups.append((group_name, list(requirements or []), scope))

        for group_name, requirements, scope in dependency_groups:
            for requirement in requirements:
                match = REQUIREMENT_NAME.match(requirement)
                if match is None:
                    raise ValueError(
                        f"cannot parse Python requirement in {manifest}: {requirement!r}"
                    )
                name = match.group(1)
                component = {
                    "type": "library",
                    "bom-ref": (
                        f"pypi-declared:{project_name}:{group_name}:{name.lower()}"
                    ),
                    "name": name,
                    "scope": scope,
                    "properties": [
                        property_item("eay:ecosystem", "pypi"),
                        property_item(
                            "eay:source-manifest",
                            str(manifest.relative_to(REPO_ROOT)),
                        ),
                        property_item("eay:dependency-group", group_name),
                        property_item("eay:declared-requirement", requirement),
                        property_item(
                            "eay:resolution-state",
                            "declared-direct-unresolved",
                        ),
                    ],
                }
                components.append(component)

    if not components:
        raise ValueError("no Python dependency declarations were discovered")
    return components


def build_bom() -> dict[str, Any]:
    components = npm_components() + python_components()
    components.sort(
        key=lambda item: (
            str(item["properties"][0]["value"]),
            str(item["name"]).lower(),
            str(item.get("version", "")),
            str(item["bom-ref"]),
        )
    )

    refs = [component["bom-ref"] for component in components]
    if len(refs) != len(set(refs)):
        raise ValueError("CycloneDX bom-ref values must remain unique")

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "lifecycles": [{"phase": "pre-build"}],
            "component": {
                "type": "application",
                "name": "EAY Platform",
                "version": "0.1.0",
            },
            "properties": [
                property_item(
                    "eay:truth-boundary",
                    "pre-build source inventory; not production/runtime evidence",
                ),
                property_item(
                    "eay:npm-resolution",
                    "resolved from package-lock.json",
                ),
                property_item(
                    "eay:python-resolution",
                    "direct declarations only; transitive runtime resolution pending build evidence",
                ),
                property_item(
                    "eay:android-resolution",
                    "not represented; resolved Android dependency graph remains pending",
                ),
            ],
        },
        "components": components,
    }


def validate_truth_boundary(bom: dict[str, Any]) -> None:
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != SPEC_VERSION:
        raise ValueError("unexpected CycloneDX document identity")
    if bom.get("metadata", {}).get("lifecycles") != [{"phase": "pre-build"}]:
        raise ValueError("SBOM must remain explicitly pre-build")

    npm = [
        component
        for component in bom["components"]
        if any(
            item == property_item("eay:ecosystem", "npm")
            for item in component.get("properties", [])
        )
    ]
    python = [
        component
        for component in bom["components"]
        if any(
            item == property_item("eay:ecosystem", "pypi")
            for item in component.get("properties", [])
        )
    ]
    if not npm or not python:
        raise ValueError("SBOM must cover both resolved npm and declared Python dependencies")
    if any(not component.get("version") for component in npm):
        raise ValueError("npm lockfile components must remain version-resolved")
    if any(not str(component.get("purl", "")).startswith("pkg:npm/") for component in npm):
        raise ValueError("npm lockfile components must expose canonical npm package URLs")
    if any("version" in component for component in python):
        raise ValueError("unresolved Python declarations must not invent component versions")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/security/eay-platform-prebuild.cdx.json"),
    )
    args = parser.parse_args()

    bom = build_bom()
    validate_truth_boundary(bom)
    validate_document(bom, source=args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bom, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    npm_count = sum(
        1
        for component in bom["components"]
        if component["bom-ref"].startswith("npm-path:")
    )
    python_count = len(bom["components"]) - npm_count
    print(
        "CycloneDX pre-build inventory: PASS "
        f"(npm_resolved={npm_count}, python_declared={python_count}, "
        "android_resolved=0, production_runtime_proof=false)"
    )


if __name__ == "__main__":
    main()
