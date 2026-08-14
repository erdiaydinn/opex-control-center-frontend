from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_provenance_manifest import (
    PROVENANCE_MANIFEST_BLOCKER,
    OrdersV2ProvenanceManifest,
    build_orders_v2_provenance_manifest,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE


def _artifact(**kwargs):
    return SimpleNamespace(**kwargs)


def _chain():
    template = ORDERS_V2_CANDIDATE.template_fingerprint
    schema = _artifact(
        artifact_fingerprint="1" * 64,
        candidate_template_fingerprint=template,
        promotion_eligible=False,
    )
    live = _artifact(
        evidence_fingerprint="2" * 64,
        schema_attestation_fingerprint=schema.artifact_fingerprint,
        candidate_template_fingerprint=template,
        promotion_eligible=False,
    )
    human = _artifact(
        review_fingerprint="3" * 64,
        schema_attestation_fingerprint=schema.artifact_fingerprint,
        live_cross_tenant_evidence_fingerprint=live.evidence_fingerprint,
        candidate_template_fingerprint=template,
        promotion_eligible=False,
        production_ready=False,
    )
    release = _artifact(
        release_gate_fingerprint="4" * 64,
        human_review_fingerprint=human.review_fingerprint,
        candidate_template_fingerprint=template,
        promotion_eligible=False,
        production_ready=False,
    )
    deployment = _artifact(
        deployment_authorization_fingerprint="5" * 64,
        human_review_fingerprint=human.review_fingerprint,
        release_gate_fingerprint=release.release_gate_fingerprint,
        candidate_template_fingerprint=template,
        promotion_eligible=False,
        production_ready=False,
    )
    proposal = _artifact(
        proposal_fingerprint="6" * 64,
        human_review_fingerprint=human.review_fingerprint,
        release_gate_fingerprint=release.release_gate_fingerprint,
        deployment_authorization_fingerprint=(
            deployment.deployment_authorization_fingerprint
        ),
        target_query_template_sha256=template,
        promotion_eligible=False,
        production_ready=False,
    )
    guard = _artifact(
        guard_fingerprint="7" * 64,
        proposal_fingerprint=proposal.proposal_fingerprint,
        promotion_eligible=False,
        production_ready=False,
    )
    review = _artifact(
        review_fingerprint="8" * 64,
        proposal_fingerprint=proposal.proposal_fingerprint,
        guard_fingerprint=guard.guard_fingerprint,
        promotion_eligible=False,
        production_ready=False,
    )
    patch = _artifact(
        patch_fingerprint="9" * 64,
        review_fingerprint=review.review_fingerprint,
        current_ledger_fingerprint="a" * 64,
        proposed_entry_fingerprint="b" * 64,
        resulting_ledger_fingerprint="c" * 64,
        promotion_eligible=False,
        production_ready=False,
    )
    commit = _artifact(
        attestation_fingerprint="d" * 64,
        patch_fingerprint=patch.patch_fingerprint,
        previous_ledger_fingerprint=patch.current_ledger_fingerprint,
        appended_entry_fingerprint=patch.proposed_entry_fingerprint,
        resulting_ledger_fingerprint=patch.resulting_ledger_fingerprint,
        promotion_eligible=False,
        production_ready=False,
    )
    return schema, live, human, release, deployment, proposal, guard, review, patch, commit


def _build(chain):
    (
        schema,
        live,
        human,
        release,
        deployment,
        proposal,
        guard,
        review,
        patch,
        commit,
    ) = chain
    return build_orders_v2_provenance_manifest(
        schema_attestation=schema,
        live_evidence=live,
        human_review=human,
        release_gate=release,
        deployment_authorization=deployment,
        policy_proposal=proposal,
        transition_guard=guard,
        consumption_review=review,
        consumption_patch=patch,
        commit_attestation=commit,
    )


def test_provenance_manifest_binds_entire_chain_without_promoting() -> None:
    manifest = _build(_chain())

    assert manifest.chain_validated is True
    assert manifest.manual_production_activation_required is True
    assert manifest.policy_mutation_permitted is False
    assert manifest.execution_enable_permitted is False
    assert manifest.promotion_eligible is False
    assert manifest.production_ready is False
    assert manifest.production_blocker == PROVENANCE_MANIFEST_BLOCKER
    assert len(manifest.manifest_fingerprint) == 64


def test_provenance_manifest_rejects_substitution_and_ledger_drift() -> None:
    chain = list(_chain())
    chain[7] = _artifact(**vars(chain[7]) | {"guard_fingerprint": "f" * 64})
    with pytest.raises(ValueError, match="guard fingerprint mismatch"):
        _build(tuple(chain))

    chain = list(_chain())
    chain[9] = _artifact(
        **vars(chain[9]) | {"resulting_ledger_fingerprint": "e" * 64}
    )
    with pytest.raises(ValueError, match="resulting ledger mismatch"):
        _build(tuple(chain))


def test_provenance_manifest_rejects_template_or_promoting_state() -> None:
    chain = list(_chain())
    chain[4] = _artifact(
        **vars(chain[4]) | {"candidate_template_fingerprint": "f" * 64}
    )
    with pytest.raises(ValueError, match="template provenance drift"):
        _build(tuple(chain))

    chain = list(_chain())
    chain[8] = _artifact(**vars(chain[8]) | {"production_ready": True})
    with pytest.raises(ValueError, match="promoting state"):
        _build(tuple(chain))


def test_provenance_manifest_model_rejects_runtime_enable_tamper() -> None:
    manifest = _build(_chain())
    payload = manifest.model_dump(mode="python")
    payload["execution_enable_permitted"] = True

    with pytest.raises(ValidationError):
        OrdersV2ProvenanceManifest.model_validate(payload)
