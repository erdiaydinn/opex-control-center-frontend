"""Materialize EAY repository configuration into the canonical cyber asset graph.

Repository presence is not deployment truth. This adapter deliberately clears all
production authority claims and refuses manifests that try to turn repository
configuration into production deployment evidence.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.cyber_attack_path_intelligence import CyberSurfaceKind
from app.cyber_continuous_defense_pipeline import (
    EayAssetInventorySnapshot,
    build_asset_inventory_snapshot,
    build_asset_observation,
    build_dependency_observation,
)
from app.cyber_defense_intelligence import AssetCriticality

CYBER_REPOSITORY_INVENTORY_CONTRACT = "eay-cyber-repository-inventory-v1"


class RepositoryAssetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_ref: str = Field(min_length=1)
    surface_kind: CyberSurfaceKind
    criticality: AssetCriticality
    product_refs: tuple[str, ...] = ()
    cpe_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    deployment_observed: bool = False
    internet_reachable: bool = False
    privileged: bool = False
    crown_jewel: bool = False

    @model_validator(mode="after")
    def repository_asset_never_claims_deployment(self) -> RepositoryAssetConfig:
        if self.deployment_observed:
            raise ValueError("repository_inventory_cannot_claim_deployment")
        return self


class RepositoryDependencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str = Field(min_length=1)
    from_asset_ref: str = Field(min_length=1)
    to_asset_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class RepositoryCyberInventoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str
    truth_class: str = Field(min_length=1)
    inventory_coverage_complete: bool = False
    production_deployment_truth_claimed: bool = False
    notes: tuple[str, ...] = ()
    assets: tuple[RepositoryAssetConfig, ...]
    dependencies: tuple[RepositoryDependencyConfig, ...]

    @model_validator(mode="after")
    def repository_manifest_is_non_authoritative(self) -> RepositoryCyberInventoryConfig:
        if self.contract != CYBER_REPOSITORY_INVENTORY_CONTRACT:
            raise ValueError("repository_inventory_contract_mismatch")
        if self.inventory_coverage_complete:
            raise ValueError("repository_inventory_cannot_claim_complete_asset_coverage")
        if self.production_deployment_truth_claimed:
            raise ValueError("repository_inventory_cannot_claim_production_truth")
        asset_refs = {asset.asset_ref for asset in self.assets}
        if len(asset_refs) != len(self.assets):
            raise ValueError("repository_inventory_duplicate_asset")
        relation_ids = {item.relation_id for item in self.dependencies}
        if len(relation_ids) != len(self.dependencies):
            raise ValueError("repository_inventory_duplicate_dependency")
        for dependency in self.dependencies:
            if dependency.from_asset_ref not in asset_refs:
                raise ValueError("repository_inventory_dependency_endpoint_missing")
            if dependency.to_asset_ref not in asset_refs:
                raise ValueError("repository_inventory_dependency_endpoint_missing")
        return self


def load_repository_inventory_config(path: Path) -> RepositoryCyberInventoryConfig:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("repository_inventory_json_object_required")
    return RepositoryCyberInventoryConfig.model_validate(raw)


def materialize_repository_inventory(
    *,
    identity: CompanyIdentity,
    config: RepositoryCyberInventoryConfig,
    observed_at: datetime,
) -> EayAssetInventorySnapshot:
    config = RepositoryCyberInventoryConfig.model_validate(config.model_dump(mode="json"))
    assets = tuple(
        build_asset_observation(
            asset_ref=item.asset_ref,
            surface_kind=item.surface_kind,
            criticality=item.criticality,
            product_refs=item.product_refs,
            cpe_refs=item.cpe_refs,
            evidence_refs=item.evidence_refs,
            observed_at=observed_at,
            recorded_at=observed_at,
            deployment_observed=False,
            internet_reachable=item.internet_reachable,
            privileged=item.privileged,
            crown_jewel=item.crown_jewel,
        )
        for item in config.assets
    )
    dependencies = tuple(
        build_dependency_observation(
            relation_id=item.relation_id,
            from_asset_ref=item.from_asset_ref,
            to_asset_ref=item.to_asset_ref,
            evidence_refs=item.evidence_refs,
            observed_at=observed_at,
            recorded_at=observed_at,
        )
        for item in config.dependencies
    )
    return build_asset_inventory_snapshot(
        identity=identity,
        assets=assets,
        dependencies=dependencies,
        as_of=observed_at,
        inventory_coverage_complete=False,
        production_deployment_truth_claimed=False,
    )
