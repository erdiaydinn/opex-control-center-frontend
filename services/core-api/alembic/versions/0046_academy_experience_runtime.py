"""Add verified playback, interactive timeline and scenario runtime authority.

Revision ID: 0046_academy_experience_runtime
Revises: 0045_academy_content_locale_expansion
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0046_academy_experience_runtime"
down_revision: str | None = "0045_academy_content_locale_expansion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
RLS_TABLES = (
    "academy_playback_sessions",
    "academy_playback_receipts",
    "academy_interaction_sets",
    "academy_interaction_nodes",
    "academy_scenarios",
    "academy_scenario_nodes",
    "academy_scenario_edges",
    "academy_scenario_runs",
    "academy_scenario_run_events",
)


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''
        CREATE POLICY "{table_name}_tenant_isolation"
        ON "{table_name}"
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        '''
    )


def upgrade() -> None:
    # Verified playback authority. Client-reported currentTime is not itself
    # learning evidence; accepted receipts advance server-authoritative coverage.
    op.execute(
        """
        CREATE TABLE academy_playback_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            enrollment_id uuid NOT NULL,
            content_version_id uuid NOT NULL,
            media_id uuid NOT NULL,
            subject varchar(255) NOT NULL,
            session_nonce char(32) NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'active',
            max_playback_rate numeric(4,2) NOT NULL DEFAULT 1.25,
            seek_tolerance_ms integer NOT NULL DEFAULT 3000,
            last_sequence integer NOT NULL DEFAULT 0,
            last_position_ms bigint NOT NULL DEFAULT 0,
            verified_until_ms bigint NOT NULL DEFAULT 0,
            verified_watch_ms bigint NOT NULL DEFAULT 0,
            revision bigint NOT NULL DEFAULT 1,
            started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_heartbeat_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at timestamptz NOT NULL,
            closed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_playback_enrollment
                FOREIGN KEY (tenant_id, enrollment_id)
                REFERENCES academy_enrollments(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT fk_academy_playback_version
                FOREIGN KEY (tenant_id, content_version_id)
                REFERENCES academy_content_versions(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_academy_playback_media
                FOREIGN KEY (tenant_id, media_id)
                REFERENCES academy_media_assets(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_academy_playback_status
                CHECK (status IN ('active', 'closed', 'expired', 'revoked')),
            CONSTRAINT ck_academy_playback_rate
                CHECK (max_playback_rate BETWEEN 0.50 AND 2.00),
            CONSTRAINT ck_academy_playback_seek_tolerance
                CHECK (seek_tolerance_ms BETWEEN 0 AND 15000),
            CONSTRAINT ck_academy_playback_positions
                CHECK (
                    last_sequence >= 0 AND
                    last_position_ms >= 0 AND
                    verified_until_ms >= 0 AND
                    verified_watch_ms >= 0
                ),
            CONSTRAINT ck_academy_playback_revision CHECK (revision > 0),
            CONSTRAINT uq_academy_playback_nonce UNIQUE (tenant_id, session_nonce),
            CONSTRAINT uq_academy_playback_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_playback_subject_active "
        "ON academy_playback_sessions(tenant_id, subject, status, expires_at)"
    )
    op.execute(
        "CREATE INDEX ix_academy_playback_enrollment_version "
        "ON academy_playback_sessions(tenant_id, enrollment_id, content_version_id)"
    )

    op.execute(
        """
        CREATE TABLE academy_playback_receipts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            playback_session_id uuid NOT NULL,
            sequence_no integer NOT NULL,
            from_position_ms bigint NOT NULL,
            to_position_ms bigint NOT NULL,
            client_elapsed_ms integer NOT NULL,
            accepted_advance_ms integer NOT NULL,
            playback_rate numeric(4,2) NOT NULL,
            visibility varchar(20) NOT NULL DEFAULT 'visible',
            receipt_hash char(64) NOT NULL,
            received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_receipt_session
                FOREIGN KEY (tenant_id, playback_session_id)
                REFERENCES academy_playback_sessions(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_academy_receipt_sequence CHECK (sequence_no > 0),
            CONSTRAINT ck_academy_receipt_positions
                CHECK (
                    from_position_ms >= 0 AND
                    to_position_ms >= from_position_ms AND
                    client_elapsed_ms >= 0 AND
                    accepted_advance_ms >= 0
                ),
            CONSTRAINT ck_academy_receipt_rate CHECK (playback_rate BETWEEN 0.25 AND 4.00),
            CONSTRAINT ck_academy_receipt_visibility
                CHECK (visibility IN ('visible', 'hidden', 'picture_in_picture')),
            CONSTRAINT ck_academy_receipt_hash CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT uq_academy_receipt_sequence
                UNIQUE (tenant_id, playback_session_id, sequence_no),
            CONSTRAINT uq_academy_receipt_hash UNIQUE (tenant_id, receipt_hash),
            CONSTRAINT uq_academy_receipt_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_receipts_session_received "
        "ON academy_playback_receipts(tenant_id, playback_session_id, received_at)"
    )

    # Interactive timeline definitions are immutable once published. Runtime
    # nodes can represent hotspot, choice, checkpoint, overlay or branching cues.
    op.execute(
        """
        CREATE TABLE academy_interaction_sets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            content_version_id uuid NOT NULL,
            version_number integer NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'draft',
            title_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_fingerprint char(64) NOT NULL,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at timestamptz,
            retired_at timestamptz,
            CONSTRAINT fk_academy_interaction_version
                FOREIGN KEY (tenant_id, content_version_id)
                REFERENCES academy_content_versions(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_academy_interaction_set_version CHECK (version_number > 0),
            CONSTRAINT ck_academy_interaction_set_status
                CHECK (status IN ('draft', 'published', 'retired')),
            CONSTRAINT ck_academy_interaction_set_fingerprint
                CHECK (source_fingerprint ~ '^[0-9a-f]{64}$'),
            CONSTRAINT uq_academy_interaction_set_version
                UNIQUE (tenant_id, content_version_id, version_number),
            CONSTRAINT uq_academy_interaction_set_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE academy_interaction_nodes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            interaction_set_id uuid NOT NULL,
            node_key varchar(120) NOT NULL,
            node_type varchar(30) NOT NULL,
            at_ms bigint NOT NULL,
            blocking boolean NOT NULL DEFAULT false,
            required boolean NOT NULL DEFAULT false,
            score_weight numeric(8,2) NOT NULL DEFAULT 0,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_interaction_node_set
                FOREIGN KEY (tenant_id, interaction_set_id)
                REFERENCES academy_interaction_sets(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_academy_interaction_node_type
                CHECK (
                    node_type IN (
                        'checkpoint', 'hotspot', 'single_choice', 'multiple_choice',
                        'drag_drop', 'overlay', 'reflection', 'branch', 'cta'
                    )
                ),
            CONSTRAINT ck_academy_interaction_node_at CHECK (at_ms >= 0),
            CONSTRAINT ck_academy_interaction_score CHECK (score_weight >= 0),
            CONSTRAINT uq_academy_interaction_node_key
                UNIQUE (tenant_id, interaction_set_id, node_key),
            CONSTRAINT uq_academy_interaction_node_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_interaction_timeline "
        "ON academy_interaction_nodes(tenant_id, interaction_set_id, at_ms)"
    )

    # Branching scenario authority for gamified operational simulations.
    op.execute(
        """
        CREATE TABLE academy_scenarios (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            scenario_key varchar(160) NOT NULL,
            version_number integer NOT NULL,
            title_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            description_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            entry_node_key varchar(120) NOT NULL,
            passing_score numeric(6,2) NOT NULL DEFAULT 80,
            status varchar(20) NOT NULL DEFAULT 'draft',
            source_fingerprint char(64) NOT NULL,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at timestamptz,
            retired_at timestamptz,
            CONSTRAINT ck_academy_scenario_version CHECK (version_number > 0),
            CONSTRAINT ck_academy_scenario_score CHECK (passing_score BETWEEN 0 AND 100),
            CONSTRAINT ck_academy_scenario_status
                CHECK (status IN ('draft', 'published', 'retired')),
            CONSTRAINT ck_academy_scenario_fingerprint
                CHECK (source_fingerprint ~ '^[0-9a-f]{64}$'),
            CONSTRAINT uq_academy_scenario_version
                UNIQUE (tenant_id, scenario_key, version_number),
            CONSTRAINT uq_academy_scenario_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE academy_scenario_nodes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            scenario_id uuid NOT NULL,
            node_key varchar(120) NOT NULL,
            node_type varchar(30) NOT NULL,
            prompt_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            terminal boolean NOT NULL DEFAULT false,
            terminal_outcome varchar(20),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_scenario_node_scenario
                FOREIGN KEY (tenant_id, scenario_id)
                REFERENCES academy_scenarios(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_academy_scenario_node_type
                CHECK (node_type IN ('scene', 'decision', 'task', 'evidence', 'outcome')),
            CONSTRAINT ck_academy_scenario_terminal_outcome
                CHECK (
                    terminal_outcome IS NULL OR
                    terminal_outcome IN ('completed', 'failed', 'remediation')
                ),
            CONSTRAINT uq_academy_scenario_node_key
                UNIQUE (tenant_id, scenario_id, node_key),
            CONSTRAINT uq_academy_scenario_node_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE academy_scenario_edges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            scenario_id uuid NOT NULL,
            from_node_key varchar(120) NOT NULL,
            choice_key varchar(120) NOT NULL,
            to_node_key varchar(120) NOT NULL,
            label_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            score_delta numeric(8,2) NOT NULL DEFAULT 0,
            correct boolean NOT NULL DEFAULT false,
            feedback_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_scenario_edge_scenario
                FOREIGN KEY (tenant_id, scenario_id)
                REFERENCES academy_scenarios(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT uq_academy_scenario_edge_choice
                UNIQUE (tenant_id, scenario_id, from_node_key, choice_key),
            CONSTRAINT uq_academy_scenario_edge_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE academy_scenario_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            scenario_id uuid NOT NULL,
            enrollment_id uuid,
            subject varchar(255) NOT NULL,
            current_node_key varchar(120) NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'in_progress',
            score numeric(8,2) NOT NULL DEFAULT 0,
            decisions integer NOT NULL DEFAULT 0,
            correct_decisions integer NOT NULL DEFAULT 0,
            revision bigint NOT NULL DEFAULT 1,
            started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_scenario_run_scenario
                FOREIGN KEY (tenant_id, scenario_id)
                REFERENCES academy_scenarios(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_academy_scenario_run_enrollment
                FOREIGN KEY (tenant_id, enrollment_id)
                REFERENCES academy_enrollments(tenant_id, id)
                ON DELETE SET NULL,
            CONSTRAINT ck_academy_scenario_run_status
                CHECK (status IN ('in_progress', 'completed', 'failed', 'remediation')),
            CONSTRAINT ck_academy_scenario_run_counts
                CHECK (
                    decisions >= 0 AND correct_decisions >= 0 AND
                    correct_decisions <= decisions AND revision > 0
                ),
            CONSTRAINT uq_academy_scenario_run_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_scenario_run_subject "
        "ON academy_scenario_runs(tenant_id, subject, status, started_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE academy_scenario_run_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            run_id uuid NOT NULL,
            sequence_no integer NOT NULL,
            node_key varchar(120) NOT NULL,
            choice_key varchar(120),
            score_delta numeric(8,2) NOT NULL DEFAULT 0,
            correct boolean,
            event_type varchar(30) NOT NULL,
            data jsonb NOT NULL DEFAULT '{}'::jsonb,
            occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_scenario_event_run
                FOREIGN KEY (tenant_id, run_id)
                REFERENCES academy_scenario_runs(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_academy_scenario_event_sequence CHECK (sequence_no > 0),
            CONSTRAINT ck_academy_scenario_event_type
                CHECK (event_type IN ('started', 'decision', 'task', 'completed', 'failed', 'remediation')),
            CONSTRAINT uq_academy_scenario_event_sequence
                UNIQUE (tenant_id, run_id, sequence_no),
            CONSTRAINT uq_academy_scenario_event_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )

    # Append-only receipts/events protect evidence history from runtime mutation.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION academy_reject_runtime_evidence_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        BEGIN
            RAISE EXCEPTION 'Academy runtime evidence is append-only';
        END;
        $body$
        """
    )
    for table_name in ("academy_playback_receipts", "academy_scenario_run_events"):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION academy_reject_runtime_evidence_mutation()
            """
        )

    for table_name in RLS_TABLES:
        _tenant_policy(table_name)

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON academy_playback_sessions TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT ON academy_playback_receipts TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON academy_interaction_sets, academy_interaction_nodes TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON academy_scenarios, academy_scenario_nodes, academy_scenario_edges, academy_scenario_runs TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT ON academy_scenario_run_events TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"REVOKE UPDATE, DELETE ON academy_playback_receipts, academy_scenario_run_events FROM {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    for table_name in reversed(RLS_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
    op.execute("DROP FUNCTION IF EXISTS academy_reject_runtime_evidence_mutation()")
