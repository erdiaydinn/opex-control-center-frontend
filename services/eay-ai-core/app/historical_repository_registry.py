from __future__ import annotations

from app.repository_intelligence import RepositoryRegistry, RepositoryRegistryError, load_repository_registry_text
from app.repository_review_snapshot import RepositoryReviewSnapshot, RepositorySnapshotError, verify_repository_review_snapshot


class HistoricalRepositoryRegistryError(ValueError):
    pass


def load_registry_for_historical_snapshot(
    registry_source_text: str,
    snapshot: RepositoryReviewSnapshot,
) -> RepositoryRegistry:
    """Load and verify the exact historical registry revision required by a snapshot.

    The caller supplies already-fetched registry text from an immutable Git revision. This function
    never falls back to the current registry: fingerprint mismatch is a hard failure.
    """
    try:
        registry = load_repository_registry_text(registry_source_text)
    except RepositoryRegistryError as exc:
        raise HistoricalRepositoryRegistryError("historical repository registry is invalid") from exc

    if registry.fingerprint != snapshot.registry_fingerprint:
        raise HistoricalRepositoryRegistryError("historical registry fingerprint does not match snapshot")

    try:
        verify_repository_review_snapshot(snapshot, registry)
    except RepositorySnapshotError as exc:
        raise HistoricalRepositoryRegistryError("snapshot is invalid under its historical registry revision") from exc
    return registry
