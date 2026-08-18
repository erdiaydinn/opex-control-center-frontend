from pathlib import Path

from app.acceptance.external_evidence import (
    EvidenceRecord,
    evaluate_requirement,
    load_requirements,
)

ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS = ROOT / "docs/governance/eay_external_acceptance_requirements.json"


def test_repository_or_synthetic_evidence_cannot_satisfy_external_gates() -> None:
    requirement = load_requirements(REQUIREMENTS)["requirements"][0]
    for evidence_class in ("REPOSITORY", "SYNTHETIC"):
        records = tuple(
            EvidenceRecord(
                requirement_key=requirement["key"],
                evidence_key=key,
                evidence_class=evidence_class,
                status="PASS",
                environment="ci",
                provenance="run:1",
                approver="ci-bot",
            )
            for key in requirement["evidence"]
        )
        ok, blockers = evaluate_requirement(requirement, records)
        assert not ok
        assert blockers
        assert all("wrong_evidence_class" in blocker for blocker in blockers)


def test_real_identity_requires_every_proof_with_complete_provenance() -> None:
    requirement = load_requirements(REQUIREMENTS)["requirements"][0]
    records = tuple(
        EvidenceRecord(
            requirement_key=requirement["key"],
            evidence_key=key,
            evidence_class="REAL_ENVIRONMENT",
            status="PASS",
            environment="corp-prod-readonly",
            provenance=f"evidence:{key}",
            approver="security-owner",
        )
        for key in requirement["evidence"]
    )
    assert evaluate_requirement(requirement, records) == (True, ())

    incomplete = list(records)
    incomplete[0] = EvidenceRecord(
        requirement_key=incomplete[0].requirement_key,
        evidence_key=incomplete[0].evidence_key,
        evidence_class=incomplete[0].evidence_class,
        status=incomplete[0].status,
        environment=incomplete[0].environment,
        provenance="",
        approver=incomplete[0].approver,
    )
    ok, blockers = evaluate_requirement(requirement, tuple(incomplete))
    assert not ok
    assert f"{incomplete[0].evidence_key}:incomplete_provenance" in blockers
