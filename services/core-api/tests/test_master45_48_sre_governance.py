from pathlib import Path

from app.sre.governance import (
    AcceptanceEvidence,
    external_gate_satisfied,
    load_sre_registry,
    production_shape_evidence_satisfied,
)

ROOT = Path(__file__).resolve().parents[3]


def test_every_service_has_owner_slo_and_external_load_boundary() -> None:
    data = load_sre_registry(ROOT / "docs/governance/eay_sre_service_registry.json")
    assert len(data["services"]) >= 9
    assert all(item["owner"] for item in data["services"])


def test_repository_and_synthetic_results_do_not_satisfy_scale_or_dr() -> None:
    assert not external_gate_satisfied(
        AcceptanceEvidence("load", "REPOSITORY", "ci", True, "run:1")
    )
    assert not external_gate_satisfied(
        AcceptanceEvidence("load", "SYNTHETIC", "ci", True, "run:2")
    )
    assert external_gate_satisfied(
        AcceptanceEvidence(
            "load",
            "MANAGED_STAGING",
            "staging",
            True,
            "run:3",
        )
    )
    assert not external_gate_satisfied(
        AcceptanceEvidence(
            "dr",
            "MANAGED_STAGING",
            "staging",
            False,
            "run:4",
        )
    )


def test_academy_media_profile_requires_real_media_environment() -> None:
    data = load_sre_registry(ROOT / "docs/governance/eay_sre_service_registry.json")
    profile = next(
        item
        for item in data["production_shape_tests"]
        if item["key"] == "academy_1200_media_concurrency"
    )
    generic = AcceptanceEvidence(
        profile["key"],
        "MANAGED_STAGING",
        "staging",
        True,
        "load:generic",
    )
    media = AcceptanceEvidence(
        profile["key"],
        "REAL_MEDIA_ENVIRONMENT",
        "media-prod-shape",
        True,
        "load:media",
    )
    assert not production_shape_evidence_satisfied(profile, generic)
    assert production_shape_evidence_satisfied(profile, media)
