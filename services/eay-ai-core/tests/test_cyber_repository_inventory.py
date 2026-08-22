from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.company_context_boundary import build_company_identity
from app.cyber_repository_inventory import (
    RepositoryCyberInventoryConfig,
    load_repository_inventory_config,
    materialize_repository_inventory,
)

NOW = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
CONFIG_PATH = Path(__file__).parents[1] / "config" / "eay_cyber_repository_inventory.json"


def _identity():
    return build_company_identity(
        tenant_id="tenant-eay",
        company_id="company-eay",
        company_slug="eay",
        profile_revision="repo-cyber-1",
        environment="repository",
    )


def test_repository_manifest_materializes_real_service_dependency_graph_without_deployment_truth():
    config = load_repository_inventory_config(CONFIG_PATH)
    snapshot = materialize_repository_inventory(
        identity=_identity(),
        config=config,
        observed_at=NOW,
    )

    asset_refs = {asset.asset_ref for asset in snapshot.assets}
    relation_ids = {relation.relation_id for relation in snapshot.dependencies}
    assert "service:core-api" in asset_refs
    assert "service:eay-ai-core" in asset_refs
    assert "service:identity-gateway" in asset_refs
    assert "package:fastapi" in asset_refs
    assert "dep:core-api:fastapi" in relation_ids
    assert "dep:eay-ai-core:httpx" in relation_ids
    assert "dep:identity-gateway:pyjwt" in relation_ids
    assert snapshot.inventory_coverage_complete is False
    assert snapshot.production_deployment_truth_claimed is False
    assert all(asset.deployment_observed is False for asset in snapshot.assets)
    assert all(not asset.cpe_refs for asset in snapshot.assets)


def test_repository_manifest_cannot_self_promote_to_production_deployment_truth():
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["production_deployment_truth_claimed"] = True
    with pytest.raises(ValueError, match="cannot_claim_production_truth"):
        RepositoryCyberInventoryConfig.model_validate(raw)


def test_repository_asset_cannot_claim_deployment_observed():
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["assets"][0]["deployment_observed"] = True
    with pytest.raises(ValueError, match="cannot_claim_deployment"):
        RepositoryCyberInventoryConfig.model_validate(raw)


def test_repository_manifest_cannot_claim_complete_asset_coverage():
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["inventory_coverage_complete"] = True
    with pytest.raises(ValueError, match="cannot_claim_complete_asset_coverage"):
        RepositoryCyberInventoryConfig.model_validate(raw)
