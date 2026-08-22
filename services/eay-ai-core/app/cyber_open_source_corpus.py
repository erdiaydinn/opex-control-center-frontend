"""Governed open-source cyber knowledge registry for defensive Jarvis use.

External repositories are knowledge/evaluation inputs only. They never grant
company truth, network authority, credential access, exploit execution, model
weight mutation, or production side effects. High-risk adversarial material is
quarantined behind the existing authorized cyber sandbox.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

CYBER_OPEN_SOURCE_CORPUS_CONTRACT = "eay-cyber-open-source-corpus-v1"
_DIGEST = r"^[0-9a-f]{64}$"
_REPO = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"


class CorpusTrustClass(str, Enum):
    L0_AUTHORITATIVE_DEFENSIVE = "L0"
    L1_CURATED_DEFENSIVE = "L1"
    L2_EDUCATIONAL_LAB = "L2"
    L3_ADVERSARIAL_KNOWLEDGE = "L3"
    L4_ADVERSARIAL_RESTRICTED = "L4"


class CorpusIngestionMode(str, Enum):
    METADATA_ONLY = "metadata_only"
    INDEX_ONLY = "index_only"
    DERIVED_CONCEPTS = "derived_concepts"
    PINNED_CONTENT = "pinned_content"
    SANDBOX_CORPUS = "sandbox_corpus"


class CorpusSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=3, max_length=120)
    owner_repo: str = Field(pattern=_REPO)
    trust_class: CorpusTrustClass
    ingestion_mode: CorpusIngestionMode
    domains: tuple[str, ...] = Field(min_length=1)
    license_spdx: str = Field(min_length=2, max_length=80)
    license_review_required: bool = True
    archived: bool = False
    meta_index: bool = False
    allow_knowledge_ingestion: bool = True
    allow_normal_rag: bool = True
    allow_code_reuse: bool = False
    allow_sandbox_execution: bool = False
    sandbox_required: bool = False
    auto_trust_linked_sources: bool = False
    supports_current_state_claim: bool = False
    company_truth_authority: bool = False
    incident_confirmation_authority: bool = False
    execution_authority_granted: bool = False
    production_execution_allowed: bool = False
    normal_chat_execution_allowed: bool = False

    @model_validator(mode="after")
    def enforce_boundaries(self) -> CorpusSource:
        if any(
            (
                self.company_truth_authority,
                self.incident_confirmation_authority,
                self.execution_authority_granted,
                self.production_execution_allowed,
                self.normal_chat_execution_allowed,
                self.auto_trust_linked_sources,
            )
        ):
            raise ValueError("external_corpus_never_mints_authority")
        if self.archived and self.supports_current_state_claim:
            raise ValueError("archived_source_cannot_support_current_truth")
        if self.trust_class is CorpusTrustClass.L4_ADVERSARIAL_RESTRICTED:
            if not self.sandbox_required or not self.allow_sandbox_execution:
                raise ValueError("l4_source_requires_authorized_sandbox")
            if self.allow_normal_rag:
                raise ValueError("l4_raw_content_forbidden_in_normal_rag")
            if self.ingestion_mode is not CorpusIngestionMode.SANDBOX_CORPUS:
                raise ValueError("l4_source_requires_sandbox_corpus_mode")
        if self.allow_sandbox_execution and not self.sandbox_required:
            raise ValueError("sandbox_execution_requires_sandbox_gate")
        if self.meta_index and self.ingestion_mode not in {
            CorpusIngestionMode.INDEX_ONLY,
            CorpusIngestionMode.METADATA_ONLY,
        }:
            raise ValueError("meta_index_must_not_be_bulk_ingested")
        if self.allow_code_reuse and self.license_review_required:
            raise ValueError("code_reuse_requires_completed_license_review")
        return self


class CorpusRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str = CYBER_OPEN_SOURCE_CORPUS_CONTRACT
    sources: tuple[CorpusSource, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral(self) -> CorpusRegistry:
        ids = [item.source_id for item in self.sources]
        repos = [item.owner_repo.lower() for item in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("corpus_source_ids_must_be_unique")
        if len(repos) != len(set(repos)):
            raise ValueError("corpus_repositories_must_be_unique")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("corpus_registry_fingerprint_mismatch")
        return self


class CorpusSnapshotReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    owner_repo: str = Field(pattern=_REPO)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    content_fingerprint: str = Field(pattern=_DIGEST)
    license_verified: bool
    provenance_verified: bool
    security_reviewed: bool
    archived_observed: bool
    company_truth_promoted: bool = False
    execution_authority_granted: bool = False
    production_execution_allowed: bool = False

    @model_validator(mode="after")
    def no_authority(self) -> CorpusSnapshotReceipt:
        if any(
            (
                self.company_truth_promoted,
                self.execution_authority_granted,
                self.production_execution_allowed,
            )
        ):
            raise ValueError("corpus_snapshot_never_mints_authority")
        return self


class IngestionDisposition(str, Enum):
    READY = "ready"
    HOLD = "hold"
    QUARANTINE = "quarantine"


class CorpusIngestionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    disposition: IngestionDisposition
    blockers: tuple[str, ...]
    normal_rag_allowed: bool
    sandbox_execution_allowed: bool
    current_state_claim_allowed: bool
    code_reuse_allowed: bool = False
    company_truth_promoted: bool = False
    execution_authority_granted: bool = False
    production_execution_allowed: bool = False

    @model_validator(mode="after")
    def no_authority(self) -> CorpusIngestionDecision:
        if any(
            (
                self.company_truth_promoted,
                self.execution_authority_granted,
                self.production_execution_allowed,
            )
        ):
            raise ValueError("corpus_decision_never_mints_authority")
        if self.disposition is IngestionDisposition.READY and self.blockers:
            raise ValueError("ready_corpus_decision_cannot_have_blockers")
        if self.disposition is not IngestionDisposition.READY and not self.blockers:
            raise ValueError("nonready_corpus_decision_requires_blocker")
        return self


def _seal(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_corpus_registry(path: str | Path) -> CorpusRegistry:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    source_payload = raw.get("sources", [])
    sources = tuple(CorpusSource.model_validate(item) for item in source_payload)
    payload = {
        "contract": CYBER_OPEN_SOURCE_CORPUS_CONTRACT,
        "sources": [item.model_dump(mode="json") for item in sources],
    }
    return CorpusRegistry.model_validate({**payload, "fingerprint": _seal(payload)})


def evaluate_corpus_snapshot(
    *,
    source: CorpusSource,
    receipt: CorpusSnapshotReceipt,
    authorized_sandbox: bool = False,
) -> CorpusIngestionDecision:
    blockers: list[str] = []
    if receipt.source_id != source.source_id or receipt.owner_repo.lower() != source.owner_repo.lower():
        blockers.append("source_snapshot_identity_mismatch")
    if not receipt.provenance_verified:
        blockers.append("source_provenance_unverified")
    if not receipt.security_reviewed:
        blockers.append("source_security_review_missing")
    if source.license_review_required and not receipt.license_verified:
        blockers.append("source_license_review_missing")
    if source.archived != receipt.archived_observed:
        blockers.append("source_archival_state_mismatch")

    restricted = source.trust_class is CorpusTrustClass.L4_ADVERSARIAL_RESTRICTED
    if restricted and not authorized_sandbox:
        blockers.append("restricted_source_authorized_sandbox_required")

    if restricted:
        disposition = (
            IngestionDisposition.READY
            if not blockers
            else IngestionDisposition.QUARANTINE
        )
    else:
        disposition = (
            IngestionDisposition.READY
            if not blockers
            else IngestionDisposition.HOLD
        )

    return CorpusIngestionDecision(
        source_id=source.source_id,
        disposition=disposition,
        blockers=tuple(dict.fromkeys(blockers)),
        normal_rag_allowed=(
            disposition is IngestionDisposition.READY and source.allow_normal_rag
        ),
        sandbox_execution_allowed=(
            disposition is IngestionDisposition.READY
            and source.allow_sandbox_execution
            and authorized_sandbox
        ),
        current_state_claim_allowed=(
            disposition is IngestionDisposition.READY
            and source.supports_current_state_claim
            and not source.archived
        ),
    )