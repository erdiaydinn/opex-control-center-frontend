"""Production-facing Master 56-60 transition adapter with just-in-time evidence revalidation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from app.acceptance.external_evidence import EvidenceRecord
from app.release.canonical_evidence_bridge import (
    CanonicalSreEvidence,
    build_canonical_external_refs,
    build_canonical_sre_refs,
)
from app.release.category_leadership import (
    REQUIRED_EXTERNAL,
    REQUIRED_SRE,
    ReleaseState,
    ReleaseTruth,
    bind_authority_ref,
    can_activate_production,
    next_state,
)


def advance_with_canonical_authority(
    repo_root: Path,
    current: ReleaseState,
    truth: ReleaseTruth,
    *,
    sre_evidence: CanonicalSreEvidence,
    external_records: tuple[EvidenceRecord, ...],
    tenant_id: str,
    as_of: datetime,
    tenant_ids: tuple[str, ...] = (),
    modules: tuple[str, ...] = (),
) -> ReleaseState:
    """Advance only after rebuilding current 45-55 authority from canonical sources.

    ``external_records`` is expected to be the complete tenant-scoped, release-scoped,
    candidate-scoped read-only ledger snapshot. The function deliberately ignores any
    pre-existing 45-55 booleans or fingerprints on ``truth`` and rebuilds them for the
    supplied ``as_of`` time before every transition.
    """

    sre_refs = build_canonical_sre_refs(repo_root, sre_evidence)
    external_refs = build_canonical_external_refs(
        repo_root,
        external_records,
        tenant_id=tenant_id,
        release_id=truth.release_id,
        candidate_sha=truth.candidate_sha,
        as_of=as_of,
    )
    if set(sre_refs) != set(REQUIRED_SRE):
        raise ValueError("current canonical 45-48 SRE evidence is incomplete")
    if set(external_refs) != set(REQUIRED_EXTERNAL):
        raise ValueError("current canonical 49-55 acceptance evidence is incomplete")

    live_truth = replace(
        truth,
        sre_items={item: True for item in REQUIRED_SRE},
        sre_evidence_refs={
            item: bind_authority_ref(
                "sre",
                sre_refs[item],
                release_id=truth.release_id,
                candidate_sha=truth.candidate_sha,
            )
            for item in REQUIRED_SRE
        },
        external_items={item: True for item in REQUIRED_EXTERNAL},
        external_evidence_refs={
            item: bind_authority_ref(
                "ledger",
                external_refs[item],
                release_id=truth.release_id,
                candidate_sha=truth.candidate_sha,
            )
            for item in REQUIRED_EXTERNAL
        },
    )

    if current == ReleaseState.PRODUCTION_ACTIVE:
        scope = live_truth.activation_scope
        if scope is None or not can_activate_production(
            live_truth,
            tenant_ids=scope.tenant_ids,
            modules=scope.modules,
        ):
            raise ValueError("stabilization entry blocked by current release authority")

    return next_state(
        current,
        live_truth,
        tenant_ids=tenant_ids,
        modules=modules,
    )
