from __future__ import annotations

from pathlib import Path

from app.repository_intelligence import (
    RepositoryRegistry,
    RepositoryRegistryError,
    load_repository_registry,
)


def validate_repository_registry_governance(
    registry: RepositoryRegistry,
) -> RepositoryRegistry:
    for entry in registry.entries:
        identity_status = entry["identity_status"]
        license_info = entry["license"]
        classification = entry["classification"]

        if identity_status == "UNRESOLVED":
            if entry["repository"] is not None or entry["canonical_upstream"] is not None:
                raise RepositoryRegistryError(
                    f"unresolved entry {entry['id']} cannot assert repository identity"
                )
            if entry["decision"] != "PENDING":
                raise RepositoryRegistryError(
                    f"unresolved entry {entry['id']} must remain PENDING"
                )
            if license_info != {"spdx": None, "status": "PENDING"}:
                raise RepositoryRegistryError(
                    f"unresolved entry {entry['id']} must keep license PENDING"
                )

        if classification == "OWN":
            if license_info["status"] != "OWN_INTERNAL_POLICY":
                raise RepositoryRegistryError(
                    f"OWN entry {entry['id']} requires OWN_INTERNAL_POLICY"
                )
        elif license_info["status"] == "OWN_INTERNAL_POLICY":
            raise RepositoryRegistryError(
                f"external entry {entry['id']} cannot use OWN_INTERNAL_POLICY"
            )

        if license_info["status"] == "VERIFIED" and not license_info["spdx"]:
            raise RepositoryRegistryError(
                f"verified license for {entry['id']} requires SPDX"
            )

    return registry


def load_governed_repository_registry(path: str | Path) -> RepositoryRegistry:
    return validate_repository_registry_governance(load_repository_registry(path))
