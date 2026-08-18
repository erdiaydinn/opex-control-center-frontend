"""Canonical exact-checkout evidence bridge for Master Roadmap 45-55 release authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.acceptance.external_evidence import (
    EvidenceRecord,
    build_external_item_refs,
    load_requirements,
)
from app.release.category_leadership import (
    build_chaos_item_ref,
    build_dr_item_ref,
    build_observability_item_ref,
    build_scale_item_ref,
)
from app.sre.chaos_dr import ChaosResult, DrResult, load_chaos_dr_contract
from app.sre.governance import AcceptanceEvidence, load_sre_registry
from app.sre.observability import TelemetryEvent, load_observability_contract


@dataclass(frozen=True)
class CanonicalSreEvidence:
    telemetry_events: tuple[TelemetryEvent, ...]
    scale_evidence: Mapping[str, AcceptanceEvidence]
    chaos_results: tuple[ChaosResult, ...]
    dr_result: DrResult
    observability_artifact_sha256: str
    scale_artifact_sha256: str
    chaos_artifact_sha256: str
    dr_artifact_sha256: str


def _canonical_path(repo_root: Path, filename: str) -> Path:
    path = repo_root / "docs" / "governance" / filename
    if not path.is_file():
        raise ValueError(f"canonical governance contract missing: {filename}")
    return path


def build_canonical_sre_refs(
    repo_root: Path,
    evidence: CanonicalSreEvidence,
) -> dict[int, str]:
    """Build 45-48 fingerprints only against version-controlled canonical contracts."""

    observability = load_observability_contract(
        _canonical_path(repo_root, "eay_observability_contract.json")
    )
    sre_registry = load_sre_registry(
        _canonical_path(repo_root, "eay_sre_service_registry.json")
    )
    chaos_dr = load_chaos_dr_contract(
        _canonical_path(repo_root, "eay_chaos_dr_acceptance.json")
    )

    return {
        45: build_observability_item_ref(
            observability,
            evidence.telemetry_events,
            artifact_sha256=evidence.observability_artifact_sha256,
        ),
        46: build_scale_item_ref(
            sre_registry,
            evidence.scale_evidence,
            artifact_sha256=evidence.scale_artifact_sha256,
        ),
        47: build_chaos_item_ref(
            chaos_dr,
            evidence.chaos_results,
            artifact_sha256=evidence.chaos_artifact_sha256,
        ),
        48: build_dr_item_ref(
            evidence.dr_result,
            artifact_sha256=evidence.dr_artifact_sha256,
        ),
    }


def build_canonical_external_refs(
    repo_root: Path,
    records: tuple[EvidenceRecord, ...],
    *,
    tenant_id: str,
    release_id: str,
    candidate_sha: str,
    as_of: datetime,
) -> dict[int, str]:
    """Build 49-55 fingerprints only from the canonical acceptance requirement matrix."""

    requirements = load_requirements(
        _canonical_path(repo_root, "eay_external_acceptance_requirements.json")
    )
    return build_external_item_refs(
        requirements,
        records,
        tenant_id=tenant_id,
        release_id=release_id,
        candidate_sha=candidate_sha,
        as_of=as_of,
    )
