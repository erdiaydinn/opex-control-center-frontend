"""Tenant-bound persistence for roadmap 16/60 manager override learning."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json

from . import persistence
from .optimizer_authority import OptimizationCandidate
from .override_learning_authority import (
    ApprovedOverrideLearningPolicy,
    OverrideLearningDraft,
    OverrideLearningObservation,
)


class OverrideLearningPersistenceError(RuntimeError):
    pass


def _enter_tenant(cursor) -> str:
    configured = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (configured,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != configured:
        raise OverrideLearningPersistenceError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    cursor.execute(
        """
        SELECT
          to_regclass('public.workforce_optimizer_proposals') IS NOT NULL,
          to_regclass('public.workforce_manager_overrides') IS NOT NULL,
          to_regclass('public.workforce_override_outcomes') IS NOT NULL,
          to_regclass('public.workforce_override_learning_drafts') IS NOT NULL,
          to_regclass('public.workforce_override_learning_versions') IS NOT NULL,
          to_regclass('public.workforce_optimizer_learning_receipts') IS NOT NULL
        """
    )
    if not all(cursor.fetchone()):
        raise OverrideLearningPersistenceError(
            "Workforce V38 override-learning schema or optimizer authority is missing"
        )
    return configured


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_manager_override(
    *,
    location_id: str,
    optimizer_proposal_fingerprint: str,
    decision: str,
    reason_code: str,
    reason_note: str | None,
    observed_action_type: str,
    actor_subject: str,
) -> dict[str, object]:
    if decision not in {"accepted", "rejected", "modified"}:
        raise OverrideLearningPersistenceError("override decision is unsupported")
    if not reason_code.strip() or not observed_action_type.strip() or not actor_subject.strip():
        raise OverrideLearningPersistenceError("override reason/action/actor are required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT location_id,dpi_snapshot_fingerprint,recommendation_type,selected_actions
            FROM workforce_optimizer_proposals
            WHERE tenant_id=%s AND proposal_fingerprint=%s
            """,
            (tenant, optimizer_proposal_fingerprint),
        )
        proposal = cursor.fetchone()
        if proposal is None:
            raise OverrideLearningPersistenceError("optimizer proposal not found in tenant authority")
        if str(proposal[0]) != location_id:
            raise OverrideLearningPersistenceError("optimizer proposal location mismatch")
        selected_actions = proposal[3] or []
        selected_action_types = {
            str(item.get("action_type"))
            for item in selected_actions
            if isinstance(item, dict) and item.get("action_type")
        }
        if decision == "accepted" and selected_action_types:
            if observed_action_type not in selected_action_types:
                raise OverrideLearningPersistenceError(
                    "accepted override action must match the governed optimizer proposal"
                )
        if decision == "accepted" and str(proposal[2]) == "no_staffing_change":
            if observed_action_type != "no_action":
                raise OverrideLearningPersistenceError(
                    "accepted no-staffing proposal must record no_action"
                )
        pre_kpi_context_ref = f"workforce-dpi://{proposal[1]}"
        source_ref = (
            f"manager-override://{optimizer_proposal_fingerprint}/{actor_subject}"
        )
        event_payload = {
            "tenant_id": tenant,
            "location_id": location_id,
            "optimizer_proposal_fingerprint": optimizer_proposal_fingerprint,
            "decision": decision,
            "reason_code": reason_code,
            "reason_note": reason_note or "",
            "observed_action_type": observed_action_type,
            "pre_kpi_context_ref": pre_kpi_context_ref,
            "actor_subject": actor_subject,
        }
        event_fingerprint = _fingerprint(event_payload)
        override_id = f"OVR-{event_fingerprint[:24]}"
        cursor.execute(
            """
            INSERT INTO workforce_manager_overrides (
              tenant_id,id,location_id,optimizer_proposal_fingerprint,decision,
              reason_code,reason_note,observed_action_type,pre_kpi_context_ref,
              actor_subject,source_ref
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id,id) DO NOTHING
            """,
            (
                tenant,
                override_id,
                location_id,
                optimizer_proposal_fingerprint,
                decision,
                reason_code,
                reason_note,
                observed_action_type,
                pre_kpi_context_ref,
                actor_subject,
                source_ref,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT optimizer_proposal_fingerprint,decision,reason_code,
                   observed_action_type,pre_kpi_context_ref,created_at
            FROM workforce_manager_overrides
            WHERE tenant_id=%s AND id=%s
            """,
            (tenant, override_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise OverrideLearningPersistenceError("manager override persistence failed")
        if (
            str(row[0]) != optimizer_proposal_fingerprint
            or str(row[1]) != decision
            or str(row[2]) != reason_code
            or str(row[3]) != observed_action_type
        ):
            raise OverrideLearningPersistenceError("manager override immutable replay mismatch")
        database.commit()
    return {
        "id": override_id,
        "tenant_id": tenant,
        "optimizer_proposal_fingerprint": str(row[0]),
        "decision": str(row[1]),
        "reason_code": str(row[2]),
        "observed_action_type": str(row[3]),
        "pre_kpi_context_ref": str(row[4]),
        "created_at": row[5],
        "idempotent_replay": not inserted,
    }


def record_override_outcome(
    *,
    override_id: str,
    worked: bool,
    post_kpi_context_ref: str,
    kpi_deltas: dict[str, Decimal],
    source_ref: str,
    actor_subject: str,
) -> dict[str, object]:
    if not post_kpi_context_ref.strip() or not source_ref.strip() or not actor_subject.strip():
        raise OverrideLearningPersistenceError("outcome KPI/source/actor provenance is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            "SELECT id FROM workforce_manager_overrides WHERE tenant_id=%s AND id=%s",
            (tenant, override_id),
        )
        if cursor.fetchone() is None:
            raise OverrideLearningPersistenceError("manager override not found in tenant authority")
        payload = {
            "override_id": override_id,
            "worked": worked,
            "post_kpi_context_ref": post_kpi_context_ref,
            "kpi_deltas": {key: str(value) for key, value in sorted(kpi_deltas.items())},
            "source_ref": source_ref,
            "actor_subject": actor_subject,
        }
        outcome_id = f"OUT-{_fingerprint(payload)[:24]}"
        cursor.execute(
            """
            INSERT INTO workforce_override_outcomes (
              tenant_id,id,override_id,worked,post_kpi_context_ref,kpi_deltas,
              source_ref,recorded_by
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT (tenant_id,override_id) DO NOTHING
            """,
            (
                tenant,
                outcome_id,
                override_id,
                worked,
                post_kpi_context_ref,
                json.dumps(payload["kpi_deltas"], sort_keys=True),
                source_ref,
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,worked,post_kpi_context_ref,kpi_deltas,created_at
            FROM workforce_override_outcomes
            WHERE tenant_id=%s AND override_id=%s
            """,
            (tenant, override_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise OverrideLearningPersistenceError("override outcome persistence failed")
        expected_deltas = payload["kpi_deltas"]
        observed_deltas = {str(key): str(value) for key, value in (row[3] or {}).items()}
        if bool(row[1]) != worked or observed_deltas != expected_deltas:
            raise OverrideLearningPersistenceError("override outcome immutable replay mismatch")
        database.commit()
    return {
        "id": str(row[0]),
        "override_id": override_id,
        "worked": bool(row[1]),
        "post_kpi_context_ref": str(row[2]),
        "kpi_deltas": row[3],
        "created_at": row[4],
        "idempotent_replay": not inserted,
    }


def load_override_learning_observations() -> tuple[OverrideLearningObservation, ...]:
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT o.id,o.optimizer_proposal_fingerprint,o.decision,o.reason_code,
                   o.observed_action_type,x.worked,o.pre_kpi_context_ref,
                   x.post_kpi_context_ref,o.source_ref
            FROM workforce_manager_overrides o
            LEFT JOIN workforce_override_outcomes x
              ON x.tenant_id=o.tenant_id AND x.override_id=o.id
            WHERE o.tenant_id=%s
            ORDER BY o.created_at,o.id
            """,
            (tenant,),
        )
        rows = cursor.fetchall()
    return tuple(
        OverrideLearningObservation(
            override_id=str(row[0]),
            optimizer_proposal_fingerprint=str(row[1]),
            decision=str(row[2]),
            reason_code=str(row[3]),
            action_type=str(row[4]),
            worked=(bool(row[5]) if row[5] is not None else None),
            pre_kpi_context_ref=str(row[6]),
            post_kpi_context_ref=(str(row[7]) if row[7] is not None else None),
            source_ref=str(row[8]),
        )
        for row in rows
    )


def persist_learning_draft(
    draft: OverrideLearningDraft,
    *,
    actor_subject: str,
) -> dict[str, object]:
    if not actor_subject.strip():
        raise OverrideLearningPersistenceError("actor_subject is required")
    draft_id = f"LRN-{draft.draft_fingerprint[:24]}"
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            INSERT INTO workforce_override_learning_drafts (
              tenant_id,id,model_family,sample_count,completed_outcome_count,
              reason_counts,frequent_override_reasons,action_success_rates,
              suggested_cost_multipliers,input_fingerprint,draft_fingerprint,
              automatic_apply_permitted,human_approval_required,created_by
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id,draft_fingerprint) DO NOTHING
            """,
            (
                tenant,
                draft_id,
                draft.model_family,
                draft.sample_count,
                draft.completed_outcome_count,
                json.dumps(draft.reason_counts, sort_keys=True),
                json.dumps(list(draft.frequent_override_reasons)),
                json.dumps({key: str(value) for key, value in draft.action_success_rates.items()}, sort_keys=True),
                json.dumps({key: str(value) for key, value in draft.suggested_cost_multipliers.items()}, sort_keys=True),
                draft.input_fingerprint,
                draft.draft_fingerprint,
                draft.automatic_apply_permitted,
                draft.human_approval_required,
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,input_fingerprint,automatic_apply_permitted,human_approval_required,created_at
            FROM workforce_override_learning_drafts
            WHERE tenant_id=%s AND draft_fingerprint=%s
            """,
            (tenant, draft.draft_fingerprint),
        )
        row = cursor.fetchone()
        if row is None or str(row[1]) != draft.input_fingerprint:
            raise OverrideLearningPersistenceError("learning draft immutable replay mismatch")
        if bool(row[2]) or not bool(row[3]):
            raise OverrideLearningPersistenceError("learning draft governance flags are invalid")
        database.commit()
    return {
        "id": str(row[0]),
        "tenant_id": tenant,
        "draft_fingerprint": draft.draft_fingerprint,
        "automatic_apply_permitted": False,
        "human_approval_required": True,
        "created_at": row[4],
        "idempotent_replay": not inserted,
    }


def load_approved_learning_policy(version: str) -> ApprovedOverrideLearningPolicy:
    if not version.strip():
        raise OverrideLearningPersistenceError("learning version is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT draft_fingerprint,action_cost_multipliers,approved_by,source_ref,
                   authority_fingerprint
            FROM workforce_override_learning_versions
            WHERE tenant_id=%s AND version=%s AND status='approved'
              AND effective_from <= now()
            """,
            (tenant, version),
        )
        rows = cursor.fetchall()
    if len(rows) != 1:
        raise OverrideLearningPersistenceError(
            "exactly one approved effective override-learning version is required"
        )
    row = rows[0]
    multipliers = {
        str(key): Decimal(str(value)) for key, value in (row[1] or {}).items()
    }
    return ApprovedOverrideLearningPolicy(
        version=version,
        draft_fingerprint=str(row[0]),
        action_cost_multipliers=multipliers,
        approved_by=str(row[2]),
        source_ref=str(row[3]),
        authority_fingerprint=str(row[4]),
    )


def _raw_candidate_pool_fingerprint(candidates: tuple[OptimizationCandidate, ...]) -> str:
    return _fingerprint(
        [candidate.canonical() for candidate in sorted(candidates, key=lambda item: item.candidate_id)]
    )


def persist_optimizer_learning_receipt(
    *,
    location_id: str,
    optimizer_proposal_fingerprint: str,
    policy: ApprovedOverrideLearningPolicy,
    raw_candidates: tuple[OptimizationCandidate, ...],
    actor_subject: str,
) -> dict[str, object]:
    raw_fingerprint = _raw_candidate_pool_fingerprint(raw_candidates)
    receipt_fingerprint = _fingerprint(
        {
            "location_id": location_id,
            "optimizer_proposal_fingerprint": optimizer_proposal_fingerprint,
            "learning_version": policy.version,
            "learning_authority_fingerprint": policy.authority_fingerprint,
            "raw_candidate_pool_fingerprint": raw_fingerprint,
        }
    )
    receipt_id = f"LRC-{receipt_fingerprint[:24]}"
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT location_id FROM workforce_optimizer_proposals
            WHERE tenant_id=%s AND proposal_fingerprint=%s
            """,
            (tenant, optimizer_proposal_fingerprint),
        )
        proposal = cursor.fetchone()
        if proposal is None or str(proposal[0]) != location_id:
            raise OverrideLearningPersistenceError(
                "learning receipt optimizer proposal is missing or misbound"
            )
        cursor.execute(
            """
            INSERT INTO workforce_optimizer_learning_receipts (
              tenant_id,id,location_id,optimizer_proposal_fingerprint,
              learning_version,learning_authority_fingerprint,
              raw_candidate_pool_fingerprint,created_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id,optimizer_proposal_fingerprint,learning_version) DO NOTHING
            """,
            (
                tenant,
                receipt_id,
                location_id,
                optimizer_proposal_fingerprint,
                policy.version,
                policy.authority_fingerprint,
                raw_fingerprint,
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        database.commit()
    return {
        "id": receipt_id,
        "learning_version": policy.version,
        "learning_authority_fingerprint": policy.authority_fingerprint,
        "raw_candidate_pool_fingerprint": raw_fingerprint,
        "idempotent_replay": not inserted,
    }


def get_learning_summary() -> dict[str, object]:
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT id,sample_count,completed_outcome_count,reason_counts,
                   frequent_override_reasons,action_success_rates,
                   suggested_cost_multipliers,draft_fingerprint,created_at
            FROM workforce_override_learning_drafts
            WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 1
            """,
            (tenant,),
        )
        draft = cursor.fetchone()
        cursor.execute(
            """
            SELECT version,draft_fingerprint,action_cost_multipliers,approved_by,
                   source_ref,authority_fingerprint,effective_from,created_at
            FROM workforce_override_learning_versions
            WHERE tenant_id=%s AND status='approved' AND effective_from <= now()
            ORDER BY effective_from DESC,created_at DESC LIMIT 1
            """,
            (tenant,),
        )
        approved = cursor.fetchone()
    return {
        "tenant_id": tenant,
        "latest_draft": (
            {
                "id": str(draft[0]),
                "sample_count": int(draft[1]),
                "completed_outcome_count": int(draft[2]),
                "reason_counts": draft[3],
                "frequent_override_reasons": draft[4],
                "action_success_rates": draft[5],
                "suggested_cost_multipliers": draft[6],
                "draft_fingerprint": str(draft[7]),
                "created_at": draft[8],
                "automatic_apply_permitted": False,
            }
            if draft is not None
            else None
        ),
        "approved_version": (
            {
                "version": str(approved[0]),
                "draft_fingerprint": str(approved[1]),
                "action_cost_multipliers": approved[2],
                "approved_by": str(approved[3]),
                "source_ref": str(approved[4]),
                "authority_fingerprint": str(approved[5]),
                "effective_from": approved[6],
                "created_at": approved[7],
            }
            if approved is not None
            else None
        ),
    }
