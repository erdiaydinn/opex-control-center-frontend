from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def create_operational_mapping(
    session: AsyncSession,
    principal: Principal,
    *,
    source_subject: str,
    source_domain: str,
    signal_type: str,
    skill_id: UUID,
    required_level: int,
    recommended_path_id: UUID,
    minimum_severity: int,
    metric_key: str,
    metric_direction: str,
    mapping_version: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO academy_operational_signal_mappings (
                    tenant_id, source_subject, source_domain, signal_type,
                    skill_id, required_level, recommended_path_id,
                    minimum_severity, metric_key, metric_direction,
                    mapping_version, created_by
                )
                SELECT
                    skill.tenant_id,
                    CAST(:source_subject AS varchar(255)),
                    CAST(:source_domain AS varchar(40)),
                    CAST(:signal_type AS varchar(160)),
                    skill.id,
                    :required_level,
                    path.id,
                    :minimum_severity,
                    CAST(:metric_key AS varchar(160)),
                    CAST(:metric_direction AS varchar(20)),
                    :mapping_version,
                    CAST(:actor AS varchar(255))
                FROM academy_skills AS skill
                JOIN academy_learning_paths AS path
                  ON path.tenant_id=skill.tenant_id
                 AND path.id=:recommended_path_id
                 AND path.status='published'
                WHERE skill.tenant_id=:tenant_id
                  AND skill.id=:skill_id
                  AND skill.status='active'
                RETURNING id, source_subject, source_domain, signal_type,
                          skill_id, required_level, recommended_path_id,
                          minimum_severity, metric_key, metric_direction,
                          mapping_version, created_by, created_at
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "source_subject": source_subject,
                "source_domain": source_domain,
                "signal_type": signal_type,
                "skill_id": skill_id,
                "required_level": required_level,
                "recommended_path_id": recommended_path_id,
                "minimum_severity": minimum_severity,
                "metric_key": metric_key,
                "metric_direction": metric_direction,
                "mapping_version": mapping_version,
                "actor": principal.subject,
            },
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def retire_operational_mapping(
    session: AsyncSession,
    principal: Principal,
    *,
    mapping_id: UUID,
    reason: str,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO academy_operational_signal_mapping_retirements (
                    tenant_id, mapping_id, reason, retired_by, request_id
                )
                SELECT mapping.tenant_id, mapping.id, CAST(:reason AS varchar(500)),
                       CAST(:actor AS varchar(255)), CAST(:request_id AS varchar(128))
                FROM academy_operational_signal_mappings AS mapping
                LEFT JOIN academy_operational_signal_mapping_retirements AS retirement
                  ON retirement.tenant_id=mapping.tenant_id
                 AND retirement.mapping_id=mapping.id
                WHERE mapping.tenant_id=:tenant_id
                  AND mapping.id=:mapping_id
                  AND retirement.id IS NULL
                RETURNING id, mapping_id, reason, retired_by, request_id, created_at
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "mapping_id": mapping_id,
                "reason": reason,
                "actor": principal.subject,
                "request_id": request_id,
            },
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def list_operational_mappings(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT mapping.id, mapping.source_subject, mapping.source_domain,
                       mapping.signal_type, mapping.skill_id, skill.skill_key,
                       skill.title_i18n AS skill_title_i18n,
                       mapping.required_level, mapping.recommended_path_id,
                       path.key AS recommended_path_key,
                       path.title_i18n AS recommended_path_title_i18n,
                       mapping.minimum_severity, mapping.metric_key,
                       mapping.metric_direction, mapping.mapping_version,
                       mapping.created_by, mapping.created_at,
                       retirement.created_at AS retired_at,
                       retirement.reason AS retirement_reason,
                       (retirement.id IS NULL) AS active
                FROM academy_operational_signal_mappings AS mapping
                JOIN academy_skills AS skill
                  ON skill.tenant_id=mapping.tenant_id AND skill.id=mapping.skill_id
                JOIN academy_learning_paths AS path
                  ON path.tenant_id=mapping.tenant_id AND path.id=mapping.recommended_path_id
                LEFT JOIN academy_operational_signal_mapping_retirements AS retirement
                  ON retirement.tenant_id=mapping.tenant_id
                 AND retirement.mapping_id=mapping.id
                WHERE mapping.tenant_id=:tenant_id
                ORDER BY mapping.created_at DESC, mapping.id DESC
                """
            ),
            {"tenant_id": principal.tenant_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def ingest_operational_signal(
    session: AsyncSession,
    principal: Principal,
    *,
    source_domain: str,
    signal_type: str,
    subject: str,
    severity: int,
    source_ref: str,
    source_version: str,
    source_fingerprint: str,
    occurred_at: object,
    request_id: str,
) -> dict[str, Any] | None:
    event = (
        await session.execute(
            text(
                """
                INSERT INTO academy_operational_signal_events (
                    tenant_id, source_subject, source_domain, signal_type,
                    subject, severity, source_ref, source_version,
                    source_fingerprint, occurred_at, request_id
                )
                SELECT membership.tenant_id, CAST(:source_subject AS varchar(255)),
                       CAST(:source_domain AS varchar(40)), CAST(:signal_type AS varchar(160)),
                       membership.external_subject, :severity,
                       CAST(:source_ref AS varchar(255)), CAST(:source_version AS varchar(120)),
                       CAST(:source_fingerprint AS char(64)), :occurred_at,
                       CAST(:request_id AS varchar(128))
                FROM memberships AS membership
                WHERE membership.tenant_id=:tenant_id
                  AND membership.external_subject=CAST(:subject AS varchar(255))
                  AND membership.status='active'
                RETURNING id, source_subject, source_domain, signal_type, subject,
                          severity, source_ref, source_version, source_fingerprint,
                          occurred_at, request_id, created_at
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "source_subject": principal.subject,
                "source_domain": source_domain,
                "signal_type": signal_type,
                "subject": subject,
                "severity": severity,
                "source_ref": source_ref,
                "source_version": source_version,
                "source_fingerprint": source_fingerprint,
                "occurred_at": occurred_at,
                "request_id": request_id,
            },
        )
    ).mappings().one_or_none()
    if event is None:
        return None

    remediations = (
        await session.execute(
            text(
                """
                INSERT INTO academy_operational_remediations (
                    tenant_id, signal_event_id, mapping_id, subject,
                    skill_id, current_level, required_level,
                    recommended_path_id, policy_version
                )
                SELECT mapping.tenant_id, :signal_event_id, mapping.id,
                       CAST(:subject AS varchar(255)), mapping.skill_id,
                       COALESCE(proficiency.observed_level, 0)::smallint,
                       mapping.required_level, mapping.recommended_path_id,
                       'operational_gap_v1'
                FROM academy_operational_signal_mappings AS mapping
                LEFT JOIN academy_operational_signal_mapping_retirements AS retirement
                  ON retirement.tenant_id=mapping.tenant_id
                 AND retirement.mapping_id=mapping.id
                LEFT JOIN academy_subject_skill_proficiency AS proficiency
                  ON proficiency.tenant_id=mapping.tenant_id
                 AND proficiency.subject=CAST(:subject AS varchar(255))
                 AND proficiency.skill_id=mapping.skill_id
                WHERE mapping.tenant_id=:tenant_id
                  AND mapping.source_subject=CAST(:source_subject AS varchar(255))
                  AND mapping.source_domain=CAST(:source_domain AS varchar(40))
                  AND mapping.signal_type=CAST(:signal_type AS varchar(160))
                  AND :severity >= mapping.minimum_severity
                  AND retirement.id IS NULL
                  AND COALESCE(proficiency.observed_level, 0) < mapping.required_level
                RETURNING id, signal_event_id, mapping_id, subject, skill_id,
                          current_level, required_level, recommended_path_id,
                          policy_version, created_at
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "signal_event_id": event["id"],
                "subject": subject,
                "source_subject": principal.subject,
                "source_domain": source_domain,
                "signal_type": signal_type,
                "severity": severity,
            },
        )
    ).mappings().all()
    return {"event": dict(event), "remediations": [dict(row) for row in remediations]}


async def record_operational_outcome(
    session: AsyncSession,
    principal: Principal,
    *,
    remediation_id: UUID,
    source_domain: str,
    source_ref: str,
    source_version: str,
    source_fingerprint: str,
    baseline_value: float,
    observed_value: float,
    window_start: object,
    window_end: object,
    observed_at: object,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO academy_operational_outcome_observations (
                    tenant_id, remediation_id, source_subject, source_domain,
                    source_ref, source_version, source_fingerprint,
                    metric_key, metric_direction, baseline_value, observed_value,
                    window_start, window_end, observed_at, recorded_by, request_id
                )
                SELECT remediation.tenant_id, remediation.id,
                       mapping.source_subject, event.source_domain,
                       CAST(:source_ref AS varchar(255)), CAST(:source_version AS varchar(120)),
                       CAST(:source_fingerprint AS char(64)), mapping.metric_key,
                       mapping.metric_direction, :baseline_value, :observed_value,
                       :window_start, :window_end, :observed_at,
                       CAST(:actor AS varchar(255)), CAST(:request_id AS varchar(128))
                FROM academy_operational_remediations AS remediation
                JOIN academy_operational_signal_events AS event
                  ON event.tenant_id=remediation.tenant_id
                 AND event.id=remediation.signal_event_id
                JOIN academy_operational_signal_mappings AS mapping
                  ON mapping.tenant_id=remediation.tenant_id
                 AND mapping.id=remediation.mapping_id
                WHERE remediation.tenant_id=:tenant_id
                  AND remediation.id=:remediation_id
                  AND mapping.source_subject=CAST(:actor AS varchar(255))
                  AND event.source_domain=CAST(:source_domain AS varchar(40))
                RETURNING id, remediation_id, source_subject, source_domain,
                          source_ref, source_version, source_fingerprint,
                          metric_key, metric_direction, baseline_value, observed_value,
                          (observed_value-baseline_value) AS observed_delta,
                          window_start, window_end, observed_at, recorded_by,
                          request_id, created_at, FALSE AS causal_attribution
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "remediation_id": remediation_id,
                "actor": principal.subject,
                "source_domain": source_domain,
                "source_ref": source_ref,
                "source_version": source_version,
                "source_fingerprint": source_fingerprint,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "window_start": window_start,
                "window_end": window_end,
                "observed_at": observed_at,
                "request_id": request_id,
            },
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def list_my_operational_readiness(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT remediation_id, subject, signal_event_id, source_domain,
                       signal_type, source_ref, source_version, source_fingerprint,
                       severity, occurred_at, skill_key, skill_title_i18n,
                       current_level, required_level, gap,
                       recommended_path_id, recommended_path_key,
                       recommended_path_title_i18n, enrollment_id, enrollment_status,
                       latest_observation_id, metric_key, metric_direction,
                       baseline_value, observed_value, observed_delta,
                       window_start, window_end, observed_at,
                       causal_attribution, policy_version, created_at
                FROM academy_operational_readiness_authority
                WHERE tenant_id=:tenant_id
                  AND subject=CAST(:subject AS varchar(255))
                ORDER BY created_at DESC, remediation_id DESC
                """
            ),
            {"tenant_id": principal.tenant_id, "subject": principal.subject},
        )
    ).mappings().all()
    return [dict(row) for row in rows]
