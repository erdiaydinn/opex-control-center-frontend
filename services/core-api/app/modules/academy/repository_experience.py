from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def create_interaction_set(
    session: AsyncSession,
    principal: Principal,
    payload: Any,
) -> dict[str, Any] | None:
    interaction = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_interaction_sets (
                        tenant_id, content_version_id, version_number, status,
                        title_i18n, source_fingerprint, created_by, published_at
                    )
                    SELECT
                        cv.tenant_id, cv.id, :version_number, :status,
                        CAST(:title_i18n AS jsonb), :source_fingerprint, :created_by,
                        CASE WHEN :status = 'published' THEN CURRENT_TIMESTAMP ELSE NULL END
                    FROM academy_content_versions AS cv
                    JOIN academy_content_items AS ci
                      ON ci.tenant_id = cv.tenant_id AND ci.id = cv.content_id
                    WHERE cv.tenant_id = :tenant_id
                      AND cv.id = :content_version_id
                      AND cv.status IN ('draft', 'published')
                      AND ci.content_type IN ('video', 'interactive', 'live')
                    RETURNING id, content_version_id, version_number, status,
                              title_i18n, source_fingerprint, created_at, published_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "content_version_id": payload.content_version_id,
                    "version_number": payload.version_number,
                    "status": payload.status,
                    "title_i18n": json_text(payload.title_i18n),
                    "source_fingerprint": payload.source_fingerprint,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if interaction is None:
        return None

    for node in payload.nodes:
        await session.execute(
            text(
                """
                INSERT INTO academy_interaction_nodes (
                    tenant_id, interaction_set_id, node_key, node_type, at_ms,
                    blocking, required, score_weight, payload
                ) VALUES (
                    :tenant_id, :interaction_set_id, :node_key, :node_type, :at_ms,
                    :blocking, :required, :score_weight, CAST(:payload AS jsonb)
                )
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "interaction_set_id": interaction["id"],
                "node_key": node.node_key,
                "node_type": node.node_type,
                "at_ms": node.at_ms,
                "blocking": node.blocking,
                "required": node.required,
                "score_weight": node.score_weight,
                "payload": json_text(node.payload),
            },
        )
    return {**dict(interaction), "node_count": len(payload.nodes)}


async def get_interaction_timeline(
    session: AsyncSession,
    principal: Principal,
    *,
    enrollment_id: UUID,
    content_version_id: UUID,
) -> dict[str, Any] | None:
    rows = (
        (
            await session.execute(
                text(
                    """
                    WITH active_set AS (
                        SELECT s.id, s.content_version_id, s.version_number,
                               s.title_i18n, s.source_fingerprint
                        FROM academy_interaction_sets AS s
                        JOIN academy_learning_path_items AS lpi
                          ON lpi.tenant_id = s.tenant_id
                         AND lpi.content_version_id = s.content_version_id
                        JOIN academy_enrollments AS e
                          ON e.tenant_id = lpi.tenant_id
                         AND e.path_id = lpi.path_id
                        WHERE s.tenant_id = :tenant_id
                          AND s.content_version_id = :content_version_id
                          AND s.status = 'published'
                          AND e.id = :enrollment_id
                          AND e.subject = :subject
                          AND e.status IN ('assigned', 'in_progress', 'completed')
                        ORDER BY s.version_number DESC
                        LIMIT 1
                    )
                    SELECT active_set.id AS interaction_set_id,
                           active_set.content_version_id,
                           active_set.version_number,
                           active_set.title_i18n,
                           active_set.source_fingerprint,
                           n.id AS node_id, n.node_key, n.node_type, n.at_ms,
                           n.blocking, n.required, n.score_weight, n.payload
                    FROM active_set
                    LEFT JOIN academy_interaction_nodes AS n
                      ON n.tenant_id = :tenant_id
                     AND n.interaction_set_id = active_set.id
                    ORDER BY n.at_ms, n.node_key
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "content_version_id": content_version_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    first = rows[0]
    return {
        "interaction_set_id": first["interaction_set_id"],
        "content_version_id": first["content_version_id"],
        "version_number": first["version_number"],
        "title_i18n": first["title_i18n"],
        "source_fingerprint": first["source_fingerprint"],
        "nodes": [
            {
                "id": row["node_id"],
                "node_key": row["node_key"],
                "node_type": row["node_type"],
                "at_ms": row["at_ms"],
                "blocking": row["blocking"],
                "required": row["required"],
                "score_weight": float(row["score_weight"] or 0),
                "payload": row["payload"],
            }
            for row in rows
            if row["node_id"] is not None
        ],
    }


async def create_scenario(
    session: AsyncSession,
    principal: Principal,
    payload: Any,
) -> dict[str, Any] | None:
    scenario = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_scenarios (
                        tenant_id, content_version_id, scenario_key, version_number,
                        title_i18n, description_i18n, entry_node_key, passing_score,
                        status, source_fingerprint, created_by, published_at
                    )
                    SELECT
                        cv.tenant_id, cv.id, :scenario_key, :version_number,
                        CAST(:title_i18n AS jsonb), CAST(:description_i18n AS jsonb),
                        :entry_node_key, :passing_score, :status,
                        :source_fingerprint, :created_by,
                        CASE WHEN :status = 'published' THEN CURRENT_TIMESTAMP ELSE NULL END
                    FROM academy_content_versions AS cv
                    JOIN academy_content_items AS ci
                      ON ci.tenant_id = cv.tenant_id AND ci.id = cv.content_id
                    WHERE cv.tenant_id = :tenant_id
                      AND cv.id = :content_version_id
                      AND cv.status IN ('draft', 'published')
                      AND ci.content_type = 'interactive'
                    RETURNING id, content_version_id, scenario_key, version_number,
                              title_i18n, description_i18n, entry_node_key,
                              passing_score, status, source_fingerprint,
                              created_at, published_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "content_version_id": payload.content_version_id,
                    "scenario_key": payload.scenario_key,
                    "version_number": payload.version_number,
                    "title_i18n": json_text(payload.title_i18n),
                    "description_i18n": json_text(payload.description_i18n),
                    "entry_node_key": payload.entry_node_key,
                    "passing_score": payload.passing_score,
                    "status": payload.status,
                    "source_fingerprint": payload.source_fingerprint,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if scenario is None:
        return None

    for node in payload.nodes:
        await session.execute(
            text(
                """
                INSERT INTO academy_scenario_nodes (
                    tenant_id, scenario_id, node_key, node_type,
                    prompt_i18n, payload, terminal, terminal_outcome
                ) VALUES (
                    :tenant_id, :scenario_id, :node_key, :node_type,
                    CAST(:prompt_i18n AS jsonb), CAST(:payload AS jsonb),
                    :terminal, :terminal_outcome
                )
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "scenario_id": scenario["id"],
                "node_key": node.node_key,
                "node_type": node.node_type,
                "prompt_i18n": json_text(node.prompt_i18n),
                "payload": json_text(node.payload),
                "terminal": node.terminal,
                "terminal_outcome": node.terminal_outcome,
            },
        )

    for edge in payload.edges:
        await session.execute(
            text(
                """
                INSERT INTO academy_scenario_edges (
                    tenant_id, scenario_id, from_node_key, choice_key,
                    to_node_key, label_i18n, score_delta, correct, feedback_i18n
                ) VALUES (
                    :tenant_id, :scenario_id, :from_node_key, :choice_key,
                    :to_node_key, CAST(:label_i18n AS jsonb), :score_delta,
                    :correct, CAST(:feedback_i18n AS jsonb)
                )
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "scenario_id": scenario["id"],
                "from_node_key": edge.from_node_key,
                "choice_key": edge.choice_key,
                "to_node_key": edge.to_node_key,
                "label_i18n": json_text(edge.label_i18n),
                "score_delta": edge.score_delta,
                "correct": edge.correct,
                "feedback_i18n": json_text(edge.feedback_i18n),
            },
        )
    return {
        **dict(scenario),
        "node_count": len(payload.nodes),
        "edge_count": len(payload.edges),
    }


async def _scenario_runtime_view(
    session: AsyncSession,
    principal: Principal,
    run_id: UUID,
) -> dict[str, Any] | None:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT r.id AS run_id, r.scenario_id, r.enrollment_id,
                           r.current_node_key, r.status, r.score, r.decisions,
                           r.correct_decisions, r.revision, r.started_at,
                           r.completed_at, s.content_version_id, s.passing_score,
                           n.node_type, n.prompt_i18n, n.payload, n.terminal,
                           n.terminal_outcome, e.choice_key, e.label_i18n
                    FROM academy_scenario_runs AS r
                    JOIN academy_scenarios AS s
                      ON s.tenant_id = r.tenant_id AND s.id = r.scenario_id
                    JOIN academy_scenario_nodes AS n
                      ON n.tenant_id = r.tenant_id
                     AND n.scenario_id = r.scenario_id
                     AND n.node_key = r.current_node_key
                    LEFT JOIN academy_scenario_edges AS e
                      ON e.tenant_id = r.tenant_id
                     AND e.scenario_id = r.scenario_id
                     AND e.from_node_key = r.current_node_key
                    WHERE r.tenant_id = :tenant_id
                      AND r.id = :run_id
                      AND r.subject = :subject
                    ORDER BY e.choice_key
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "run_id": run_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    first = rows[0]
    return {
        "run_id": first["run_id"],
        "scenario_id": first["scenario_id"],
        "enrollment_id": first["enrollment_id"],
        "content_version_id": first["content_version_id"],
        "current_node_key": first["current_node_key"],
        "status": first["status"],
        "score": float(first["score"]),
        "passing_score": float(first["passing_score"]),
        "decisions": first["decisions"],
        "correct_decisions": first["correct_decisions"],
        "revision": first["revision"],
        "started_at": first["started_at"],
        "completed_at": first["completed_at"],
        "node": {
            "node_key": first["current_node_key"],
            "node_type": first["node_type"],
            "prompt_i18n": first["prompt_i18n"],
            "payload": first["payload"],
            "terminal": first["terminal"],
            "terminal_outcome": first["terminal_outcome"],
            "choices": [
                {
                    "choice_key": row["choice_key"],
                    "label_i18n": row["label_i18n"],
                }
                for row in rows
                if row["choice_key"] is not None
            ],
        },
    }


async def start_scenario_run(
    session: AsyncSession,
    principal: Principal,
    *,
    scenario_id: UUID,
    enrollment_id: UUID,
) -> dict[str, Any] | None:
    run_id = uuid4()
    run = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_scenario_runs (
                        id, tenant_id, scenario_id, enrollment_id, subject,
                        current_node_key, status
                    )
                    SELECT
                        :run_id, s.tenant_id, s.id, e.id, e.subject,
                        s.entry_node_key, 'in_progress'
                    FROM academy_scenarios AS s
                    JOIN academy_learning_path_items AS lpi
                      ON lpi.tenant_id = s.tenant_id
                     AND lpi.content_version_id = s.content_version_id
                    JOIN academy_enrollments AS e
                      ON e.tenant_id = lpi.tenant_id AND e.path_id = lpi.path_id
                    WHERE s.tenant_id = :tenant_id
                      AND s.id = :scenario_id
                      AND s.status = 'published'
                      AND e.id = :enrollment_id
                      AND e.subject = :subject
                      AND e.status IN ('assigned', 'in_progress')
                    RETURNING id, scenario_id, enrollment_id, current_node_key,
                              status, score, decisions, correct_decisions,
                              revision, started_at
                    """
                ),
                {
                    "run_id": run_id,
                    "tenant_id": principal.tenant_id,
                    "scenario_id": scenario_id,
                    "enrollment_id": enrollment_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        return None
    await session.execute(
        text(
            """
            INSERT INTO academy_scenario_run_events (
                tenant_id, run_id, sequence_no, node_key, event_type, data
            ) VALUES (
                :tenant_id, :run_id, 1, :node_key, 'started', '{}'::jsonb
            )
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "run_id": run_id,
            "node_key": run["current_node_key"],
        },
    )
    return await _scenario_runtime_view(session, principal, run_id)


async def apply_scenario_decision(
    session: AsyncSession,
    principal: Principal,
    *,
    run_id: UUID,
    choice_key: str,
    expected_revision: int,
) -> dict[str, Any] | None:
    transition = (
        (
            await session.execute(
                text(
                    """
                    SELECT r.scenario_id, r.enrollment_id, r.current_node_key,
                           r.score, r.decisions, r.correct_decisions, r.revision,
                           e.to_node_key, e.score_delta, e.correct,
                           target.terminal, target.terminal_outcome
                    FROM academy_scenario_runs AS r
                    JOIN academy_scenario_edges AS e
                      ON e.tenant_id = r.tenant_id
                     AND e.scenario_id = r.scenario_id
                     AND e.from_node_key = r.current_node_key
                     AND e.choice_key = :choice_key
                    JOIN academy_scenario_nodes AS target
                      ON target.tenant_id = r.tenant_id
                     AND target.scenario_id = r.scenario_id
                     AND target.node_key = e.to_node_key
                    WHERE r.tenant_id = :tenant_id
                      AND r.id = :run_id
                      AND r.subject = :subject
                      AND r.status = 'in_progress'
                      AND r.revision = :expected_revision
                    FOR UPDATE OF r
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "run_id": run_id,
                    "subject": principal.subject,
                    "choice_key": choice_key,
                    "expected_revision": expected_revision,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if transition is None:
        return None

    terminal = bool(transition["terminal"])
    terminal_outcome = transition["terminal_outcome"] if terminal else None
    new_status = terminal_outcome or "in_progress"
    new_score = max(0.0, min(100.0, float(transition["score"]) + float(transition["score_delta"])))
    updated = (
        (
            await session.execute(
                text(
                    """
                    UPDATE academy_scenario_runs
                    SET current_node_key = :to_node_key,
                        status = :status,
                        score = :score,
                        decisions = decisions + 1,
                        correct_decisions = correct_decisions + CASE WHEN :correct THEN 1 ELSE 0 END,
                        revision = revision + 1,
                        completed_at = CASE
                            WHEN :terminal THEN CURRENT_TIMESTAMP ELSE completed_at END
                    WHERE tenant_id = :tenant_id
                      AND id = :run_id
                      AND subject = :subject
                      AND status = 'in_progress'
                      AND revision = :expected_revision
                    RETURNING id, revision, status
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "run_id": run_id,
                    "subject": principal.subject,
                    "to_node_key": transition["to_node_key"],
                    "status": new_status,
                    "score": new_score,
                    "correct": bool(transition["correct"]),
                    "terminal": terminal,
                    "expected_revision": expected_revision,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if updated is None:
        return None

    sequence_no = int(transition["decisions"]) + 2
    event_type = new_status if terminal else "decision"
    await session.execute(
        text(
            """
            INSERT INTO academy_scenario_run_events (
                tenant_id, run_id, sequence_no, node_key, choice_key,
                score_delta, correct, event_type, data
            ) VALUES (
                :tenant_id, :run_id, :sequence_no, :node_key, :choice_key,
                :score_delta, :correct, :event_type, '{}'::jsonb
            )
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "run_id": run_id,
            "sequence_no": sequence_no,
            "node_key": transition["current_node_key"],
            "choice_key": choice_key,
            "score_delta": transition["score_delta"],
            "correct": transition["correct"],
            "event_type": event_type,
        },
    )
    return await _scenario_runtime_view(session, principal, run_id)
