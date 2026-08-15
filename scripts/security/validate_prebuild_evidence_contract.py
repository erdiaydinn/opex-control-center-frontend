#!/usr/bin/env python3
"""Fail closed when build-phase dependency evidence overclaims runtime truth.

This validator is intentionally narrow: repository/CI dependency inventories may
prove what a build environment, lockfile, or resolved build graph contained.
They must never be relabeled as production runtime/deployment attestation,
reachability proof, or production readiness without separate real-environment
evidence and approval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_LIFECYCLES = {"pre-build", "build"}
REQUIRED_BOUNDARY_TERMS = ("not production", "runtime")
FORBIDDEN_TRUE_CLAIMS = (
    "production_runtime_proof=true",
    "production-ready=true",
    "production_ready=true",
    "deployment_attestation=true",
    "runtime_attestation=true",
    "reachability_proof=true",
)


def property_map(document: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in document.get("metadata", {}).get("properties", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        value = str(item.get("value", "")).strip()
        if name:
            result[name] = value
    return result


def validate_document(document: dict[str, Any], *, source: Path) -> None:
    if document.get("bomFormat") != "CycloneDX":
        raise ValueError(f"{source}: evidence must be CycloneDX")

    lifecycle_items = document.get("metadata", {}).get("lifecycles") or []
    phases = {
        str(item.get("phase", "")).strip()
        for item in lifecycle_items
        if isinstance(item, dict)
    }
    if len(phases) != 1 or not phases.issubset(ALLOWED_LIFECYCLES):
        raise ValueError(
            f"{source}: dependency evidence lifecycle must be exactly pre-build or build"
        )

    properties = property_map(document)
    boundary = properties.get("eay:truth-boundary", "").lower()
    if not boundary:
        raise ValueError(f"{source}: eay:truth-boundary is required")
    for term in REQUIRED_BOUNDARY_TERMS:
        if term not in boundary:
            raise ValueError(
                f"{source}: truth boundary must explicitly contain {term!r}"
            )

    serialized = json.dumps(document, sort_keys=True).lower().replace(" ", "_")
    for forbidden in FORBIDDEN_TRUE_CLAIMS:
        if forbidden in serialized:
            raise ValueError(
                f"{source}: repository dependency evidence overclaims production truth: "
                f"{forbidden}"
            )

    components = document.get("components") or []
    if not isinstance(components, list) or not components:
        raise ValueError(f"{source}: dependency evidence must contain components")

    refs = [str(component.get("bom-ref", "")).strip() for component in components]
    if any(not ref for ref in refs) or len(refs) != len(set(refs)):
        raise ValueError(f"{source}: component bom-ref values must be unique and non-empty")

    for component in components:
        if not isinstance(component, dict):
            raise ValueError(f"{source}: components must be objects")
        props = {
            str(item.get("name", "")): str(item.get("value", ""))
            for item in component.get("properties", []) or []
            if isinstance(item, dict)
        }
        resolution = props.get("eay:resolution-state", "")
        if resolution == "declared-direct-unresolved" and "version" in component:
            raise ValueError(
                f"{source}: unresolved declared dependency must not invent a version"
            )
        if resolution in {"installed-build-environment", "gradle-build-resolved"}:
            if not str(component.get("version", "")).strip():
                raise ValueError(
                    f"{source}: resolved build dependency must contain an exact version"
                )


def load_and_validate(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: top-level CycloneDX document must be an object")
    validate_document(document, source=path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    for path in args.inputs:
        load_and_validate(path)

    print(
        "EAY pre-build evidence truth contract: PASS "
        f"(documents={len(args.inputs)}, production_runtime_proof=false)"
    )


if __name__ == "__main__":
    main()
