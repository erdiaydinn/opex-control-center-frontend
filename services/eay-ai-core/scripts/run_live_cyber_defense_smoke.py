"""Live, read-only public threat-intelligence smoke for Jarvis cyber defense."""

from __future__ import annotations

from datetime import UTC, datetime

from app.cyber_continuous_defense_pipeline import (
    LiveThreatFeedClient,
    ingest_live_public_threat,
    latest_kev_cve_id,
)


def main() -> int:
    observed_at = datetime.now(UTC)
    client = LiveThreatFeedClient(timeout_seconds=20.0)
    try:
        kev_payload, kev_observation = client.fetch_kev_catalog(observed_at=observed_at)
        cve_id = latest_kev_cve_id(kev_payload)
        receipt = ingest_live_public_threat(
            client=client,
            cve_id=cve_id,
            as_of=observed_at,
        )
    finally:
        client.close()

    kev_source = next(
        item for item in receipt.source_observations if item.source.value == "cisa_kev"
    )
    print(f"LIVE_CYBER_CVE={receipt.cve_id}")
    print(f"LIVE_CYBER_KEV_TRANSPORT={kev_source.transport.value}")
    print(
        "LIVE_CYBER_KEV_CANONICAL_AUTHORITY_OBSERVED="
        f"{str(kev_source.canonical_authority_observed).lower()}"
    )
    print(f"LIVE_CYBER_NVD_CURRENT={str(receipt.current_nvd_observed).lower()}")
    print(f"LIVE_CYBER_EPSS_CURRENT={str(receipt.current_epss_observed).lower()}")
    print(
        "LIVE_CYBER_KNOWN_EXPLOITED="
        f"{str(receipt.primary_threat.known_exploited_in_wild).lower()}"
    )
    print(f"LIVE_CYBER_COMPANY_TRUTH={str(receipt.company_truth_granted).lower()}")
    print(
        "LIVE_CYBER_EXECUTION_AUTHORITY="
        f"{str(receipt.execution_authority_granted).lower()}"
    )

    if not receipt.current_nvd_observed:
        raise RuntimeError("live_cyber_nvd_observation_required")
    if not receipt.primary_threat.known_exploited_in_wild:
        raise RuntimeError("live_cyber_latest_kev_must_remain_known_exploited")
    if receipt.company_truth_granted or receipt.execution_authority_granted:
        raise RuntimeError("live_cyber_public_feed_authority_boundary_broken")
    if kev_observation.fingerprint != kev_source.fingerprint:
        raise RuntimeError("live_cyber_kev_observation_binding_mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
