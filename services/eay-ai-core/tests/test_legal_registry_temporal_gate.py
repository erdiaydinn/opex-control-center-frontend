from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_promotion_gate import LegalPromotionCandidate, evaluate_legal_promotion
from app.legal_registry_discovery import RegistryDiscoveryCandidate, load_consumer_registry_manifest
from app.legal_registry_temporal_gate import build_registry_temporal_promotion_evidence
from app.legal_registry_verification_intake import build_registry_bound_verification_intake
from app.legal_relations import LegalRelationStore
from app.legal_temporal import LegalTemporalResolver
from app.regulatory_authority import assess_regulatory_authority


PUBLICATION_URL = "https://www.resmigazete.gov.tr/eskiler/2026/06/20260601-1.htm"
PUBLICATION_TEXT = (
    "1 Haziran 2026 Resmî Gazete Sayı : 33000\n"
    "MADDE 1 - Bu metin temporal registry regression kanıtı için exact publication fixture'dır."
)


def _registry_candidate():
    manifest = load_consumer_registry_manifest()
    instrument = manifest.instruments[0]
    return (
        RegistryDiscoveryCandidate(
            instrument_key=instrument.key,
            title=instrument.title,
            registry_url=str(manifest.registry_url),
            registry_manifest_fingerprint=manifest.manifest_fingerprint,
            expected_registry_target_url=str(instrument.registry_target_url),
            discovered_url=str(instrument.registry_target_url),
            discovered_host="www.mevzuat.gov.tr",
        ),
        manifest,
    )


def _promotion_review(intake):
    authority = assess_regulatory_authority(
        source_id="resmi-gazete-exact",
        source_role="binding_publication_index",
        document_url=PUBLICATION_URL,
        text=PUBLICATION_TEXT,
    )
    candidate = LegalPromotionCandidate(
        instrument_id=intake.instrument_key,
        authoritative_url=intake.exact_binding_url,
        authoritative_text=PUBLICATION_TEXT,
        expected_content_sha256=intake.exact_binding_content_sha256,
        publication_date=intake.publication_date,
        effective_from=intake.effective_from,
        authority_assessment=authority,
        relation_type=intake.relation_type,
        related_instrument_id=intake.related_instrument_id,
        human_approval_ref="LEGAL-REGISTRY-TEMPORAL-REVIEW-1",
    )
    decision = evaluate_legal_promotion(candidate)
    assert decision.eligible is True
    assert decision.auto_promote is False
    return decision


def _upsert_verified(engine, instrument_id: str, *, publication: date, effective: date):
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id=instrument_id,
            title=instrument_id,
            instrument_type="regulation",
            publication_date=publication,
            effective_from=effective,
            source_url=PUBLICATION_URL,
            verification_status="verified",
        )
    )


def _supersession_scenario(tmp_path):
    registry_candidate, manifest = _registry_candidate()
    target_id = "legacy-consumer-instrument"
    intake = build_registry_bound_verification_intake(
        registry_candidate,
        manifest,
        authoritative_url=PUBLICATION_URL,
        authoritative_text=PUBLICATION_TEXT,
        publication_date=date(2026, 6, 1),
        effective_from=date(2026, 7, 1),
        official_gazette_number="33000",
        relation_type="supersedes",
        related_instrument_id=target_id,
    )
    decision = _promotion_review(intake)

    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _upsert_verified(engine, target_id, publication=date(2025, 1, 1), effective=date(2025, 1, 1))
    _upsert_verified(
        engine,
        intake.instrument_key,
        publication=intake.publication_date,
        effective=intake.effective_from,
    )
    relations = LegalRelationStore(db)
    relation = relations.propose(
        source_instrument_id=intake.instrument_key,
        relation_type="supersedes",
        target_instrument_id=target_id,
        evidence_ref=f"registry-intake:{intake.intake_fingerprint}",
    )
    relation = relations.decide(
        relation.id,
        decision="approved",
        reviewer_ref="LEGAL-TEMPORAL-REVIEWER-2",
    )
    state = LegalTemporalResolver(db).resolve(date(2026, 7, 1))
    return intake, decision, relation, state, target_id


def test_registry_supersession_requires_resolved_inactive_old_version(tmp_path):
    intake, decision, relation, state, target_id = _supersession_scenario(tmp_path)

    evidence = build_registry_temporal_promotion_evidence(
        intake,
        decision,
        state,
        relation=relation,
    )

    assert evidence.instrument_id == intake.instrument_key
    assert target_id in state.inactive_instrument_ids
    assert target_id not in state.active_instrument_ids
    assert evidence.expected_temporal_effect_observed is True
    assert evidence.legal_activation_permitted is False
    assert evidence.registry_mutation_permitted is False
    assert evidence.auto_promote is False
    assert len(evidence.evidence_fingerprint) == 64


def test_registry_supersession_rejects_stale_target_remaining_active(tmp_path):
    intake, decision, relation, state, target_id = _supersession_scenario(tmp_path)
    tampered = replace(
        state,
        active_instrument_ids=tuple(sorted((*state.active_instrument_ids, target_id))),
        inactive_instrument_ids=(),
    )

    with pytest.raises(ValueError, match="inactive_target_required"):
        build_registry_temporal_promotion_evidence(
            intake,
            decision,
            tampered,
            relation=relation,
        )


def test_registry_supersession_rejects_unapproved_relation(tmp_path):
    intake, decision, relation, state, _ = _supersession_scenario(tmp_path)
    pending = replace(relation, status="pending")

    with pytest.raises(ValueError, match="relation_must_be_approved"):
        build_registry_temporal_promotion_evidence(
            intake,
            decision,
            state,
            relation=pending,
        )


def test_registry_temporal_gate_rejects_pre_effective_state(tmp_path):
    intake, decision, relation, state, _ = _supersession_scenario(tmp_path)
    early = replace(state, as_of="2026-06-30")

    with pytest.raises(ValueError, match="state_precedes_effective_date"):
        build_registry_temporal_promotion_evidence(
            intake,
            decision,
            early,
            relation=relation,
        )
