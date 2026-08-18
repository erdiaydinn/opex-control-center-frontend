"""Master 40 provenance-bound repository impact graph."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.repository_intelligence.registry import RepositoryEntry

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class RepoSnapshot:
    registry_id: str
    repository: str
    commit_sha: str
    branch_or_tag: str
    paths: tuple[str, ...]
    symbols: tuple[str, ...]
    contracts: tuple[str, ...]
    owners: tuple[str, ...]
    license_status: str
    decision: str


@dataclass(frozen=True)
class ImpactEdge:
    source_registry_id: str
    target_registry_id: str
    contract: str
    reason: str


def validate_snapshot(snapshot: RepoSnapshot) -> None:
    if not _REPOSITORY.fullmatch(snapshot.repository):
        raise ValueError("repository snapshot requires exact owner/repo identity")
    if not _SHA40.fullmatch(snapshot.commit_sha.lower()):
        raise ValueError("repository snapshot requires exact commit SHA")
    if not snapshot.branch_or_tag.strip():
        raise ValueError("repository snapshot requires branch or tag provenance")
    provenance_values = (*snapshot.paths, *snapshot.symbols, *snapshot.contracts)
    if any(not value.strip() for value in provenance_values):
        raise ValueError("repository snapshot contains empty provenance values")


def validate_snapshot_against_registry(
    snapshot: RepoSnapshot,
    entry: RepositoryEntry,
) -> None:
    validate_snapshot(snapshot)
    if snapshot.registry_id != entry.registry_id:
        raise ValueError("snapshot registry identity does not match registry entry")
    if entry.identity_status != "VERIFIED" or not entry.analysis_permitted:
        raise ValueError("registry entry is not approved for repository analysis")
    if snapshot.repository != entry.repository:
        raise ValueError("snapshot repository does not match verified registry identity")
    if snapshot.license_status != entry.license_status or snapshot.decision != entry.decision:
        raise ValueError("snapshot license/decision drifted from registry authority")


def snapshot_usable_as_code_source(
    snapshot: RepoSnapshot,
    entry: RepositoryEntry,
) -> bool:
    try:
        validate_snapshot_against_registry(snapshot, entry)
    except ValueError:
        return False
    return entry.usable_as_code_source


def build_impact_edges(snapshots: Iterable[RepoSnapshot]) -> tuple[ImpactEdge, ...]:
    items = tuple(snapshots)
    for item in items:
        validate_snapshot(item)

    edges: list[ImpactEdge] = []
    for source in items:
        source_contracts = set(source.contracts)
        for target in items:
            if source.registry_id == target.registry_id:
                continue
            shared = sorted(source_contracts & set(target.contracts))
            edges.extend(
                ImpactEdge(
                    source_registry_id=source.registry_id,
                    target_registry_id=target.registry_id,
                    contract=contract,
                    reason="shared_contract",
                )
                for contract in shared
            )
    return tuple(
        sorted(
            edges,
            key=lambda edge: (
                edge.contract,
                edge.source_registry_id,
                edge.target_registry_id,
            ),
        )
    )


def repo_question_context(
    *,
    snapshots: Iterable[RepoSnapshot],
    question_terms: tuple[str, ...],
) -> tuple[RepoSnapshot, ...]:
    terms = {term.casefold() for term in question_terms if term.strip()}
    if not terms:
        return ()

    selected: list[RepoSnapshot] = []
    for snapshot in snapshots:
        validate_snapshot(snapshot)
        haystack = " ".join(
            (
                snapshot.repository,
                snapshot.branch_or_tag,
                *snapshot.paths,
                *snapshot.symbols,
                *snapshot.contracts,
            )
        ).casefold()
        if any(term in haystack for term in terms):
            selected.append(snapshot)
    return tuple(
        sorted(
            selected,
            key=lambda snapshot: (snapshot.repository, snapshot.commit_sha),
        )
    )
