from __future__ import annotations

import re
from typing import Any

from .repository_candidate_evidence import validate_candidate_evidence
from .repository_intelligence import RepositoryRegistry, RepositoryRegistryError

_LOCAL_MTIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
_REQUIRED_OBSERVATION_FIELDS = {
    "size_bytes",
    "observed_local_mtime",
    "source_kind",
    "source_trust",
    "promotion_effect",
}


def validate_archive_inventory_observations(
    registry: RepositoryRegistry,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate non-cryptographic supplied-archive inventory observations.

    Directory listings can prove that a named archive was observed with a particular size and
    local timestamp, but they cannot prove bytes, Git identity, upstream ownership, or license.
    These observations therefore remain explicitly non-promoting and may only help locate the
    original archive for a later SHA-256/blob/tree verification pass.
    """

    validate_candidate_evidence(registry, payload)

    for candidate in payload["candidates"]:
        entry_id = candidate["registry_entry_id"]
        observation = candidate.get("archive_inventory_observation")
        if not isinstance(observation, dict):
            raise RepositoryRegistryError(
                f"candidate archive inventory observation is required: {entry_id}"
            )
        if set(observation) != _REQUIRED_OBSERVATION_FIELDS:
            raise RepositoryRegistryError(
                f"candidate archive inventory observation must use exact reviewed fields: {entry_id}"
            )

        size_bytes = observation["size_bytes"]
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
            raise RepositoryRegistryError(
                f"candidate archive inventory size_bytes must be a positive integer: {entry_id}"
            )

        observed_local_mtime = observation["observed_local_mtime"]
        if not isinstance(observed_local_mtime, str) or not _LOCAL_MTIME_RE.fullmatch(
            observed_local_mtime
        ):
            raise RepositoryRegistryError(
                f"candidate archive inventory local mtime must be YYYY-MM-DDTHH:MM:SS: {entry_id}"
            )

        if observation["source_kind"] != "USER_DIRECTORY_LISTING":
            raise RepositoryRegistryError(
                f"candidate archive inventory source_kind is not reviewed: {entry_id}"
            )
        if observation["source_trust"] != "NON_CRYPTOGRAPHIC_DIRECTORY_LISTING":
            raise RepositoryRegistryError(
                f"candidate archive inventory must remain non-cryptographic: {entry_id}"
            )
        if observation["promotion_effect"] != "NONE":
            raise RepositoryRegistryError(
                f"candidate archive inventory may not affect promotion: {entry_id}"
            )

    return payload
