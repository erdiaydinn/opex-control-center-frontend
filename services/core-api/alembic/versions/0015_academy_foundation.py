"""Create EAY Academy production foundation.

Revision ID: 0015_academy_foundation
Revises: 0014_budget_rls_controls
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_academy_foundation"
down_revision: str | None = "0014_budget_rls_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
ACADEMY_TABLES = (
    "academy_content_items",
    "academy_content_versions",
    "academy_media_assets",
    "academy_learning_paths",
    "academy_learning_path_items",
    "academy_path_role_assignments",
    "academy_enrollments",
    "academy_progress",
    "academy_quizzes",
    "academy_questions",
    "academy_question_options",
    "academy_quiz_attempts",
    "academy_quiz_answers",
    "academy_certificates",
    "academy_entitlements",
    "academy_learning_events",
    "academy_idempotency_keys",
    "academy_document_chunks",
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


def _execute_statements(statements: tuple[str, ...]) -> None:
    """Execute each DDL statement independently inside Alembic's transaction."""
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _execute_statements(
        (
            """
            CREATE TABLE academy_content_items (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                content_type varchar(20) NOT NULL,
                slug varchar(180) NOT NULL,
                title_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
                description_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
                status varchar(20) NOT NULL DEFAULT 'draft',
                created_by varchar(255) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_academy_content_type
                    CHECK (content_type IN ('document', 'video', 'sop')),
                CONSTRAINT ck_academy_content_status
                    CHECK (status IN ('draft', 'published', 'retired')),
                CONSTRAINT uq_academy_content_slug UNIQUE (tenant_id, slug),
                CONSTRAINT uq_academy_content_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_content_versions (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                content_id uuid NOT NULL,
                version_label varchar(80) NOT NULL,
                version_number integer NOT NULL DEFAULT 1,
                locale varchar(5) NOT NULL DEFAULT 'tr',
                mime_type varchar(160),
                source_sha256 char(64),
                storage_key varchar(1024),
                delivery_key varchar(512),
                size_bytes bigint,
                duration_ms bigint,
                accessibility_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                status varchar(20) NOT NULL DEFAULT 'draft',
                published_at timestamptz,
                effective_at timestamptz,
                retired_at timestamptz,
                created_by varchar(255) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_content_version_item
                    FOREIGN KEY (tenant_id, content_id)
                    REFERENCES academy_content_items(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT ck_academy_content_version_locale
                    CHECK (locale IN ('tr', 'en', 'de', 'ar')),
                CONSTRAINT ck_academy_content_version_status
                    CHECK (status IN ('draft', 'published', 'retired')),
                CONSTRAINT ck_academy_source_sha
                    CHECK (source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'),
                CONSTRAINT ck_academy_content_version_number CHECK (version_number > 0),
                CONSTRAINT uq_academy_content_version_label
                    UNIQUE (tenant_id, content_id, version_label, locale),
                CONSTRAINT uq_academy_content_version_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_media_assets (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                content_version_id uuid NOT NULL,
                asset_kind varchar(30) NOT NULL,
                storage_provider varchar(20) NOT NULL,
                storage_bucket varchar(255) NOT NULL,
                storage_key varchar(1024) NOT NULL,
                delivery_key varchar(512) NOT NULL,
                manifest_path varchar(512),
                checksum_sha256 char(64) NOT NULL,
                size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
                duration_ms bigint,
                transcode_status varchar(20) NOT NULL DEFAULT 'ready',
                delivery_mode varchar(20) NOT NULL DEFAULT 'hls',
                encryption_mode varchar(30) NOT NULL DEFAULT 'edge_token',
                segment_duration_seconds smallint NOT NULL DEFAULT 6,
                created_by varchar(255) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_media_content_version
                    FOREIGN KEY (tenant_id, content_version_id)
                    REFERENCES academy_content_versions(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT ck_academy_media_provider
                    CHECK (storage_provider IN ('s3', 'gcs', 'azure', 'minio')),
                CONSTRAINT ck_academy_media_kind
                    CHECK (asset_kind IN ('video_hls', 'video_dash', 'document')),
                CONSTRAINT ck_academy_media_status
                    CHECK (transcode_status IN ('pending', 'ready', 'failed', 'retired')),
                CONSTRAINT ck_academy_delivery_mode
                    CHECK (delivery_mode IN ('hls', 'dash', 'document')),
                CONSTRAINT ck_academy_media_checksum
                    CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
                CONSTRAINT ck_academy_segment_duration
                    CHECK (segment_duration_seconds BETWEEN 2 AND 12),
                CONSTRAINT uq_academy_media_delivery_key UNIQUE (tenant_id, delivery_key),
                CONSTRAINT uq_academy_media_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_learning_paths (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                key varchar(160) NOT NULL,
                title_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
                description_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
                certificate_enabled boolean NOT NULL DEFAULT true,
                completion_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
                status varchar(20) NOT NULL DEFAULT 'draft',
                created_by varchar(255) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_academy_path_status CHECK (status IN ('draft', 'published', 'retired')),
                CONSTRAINT uq_academy_path_key UNIQUE (tenant_id, key),
                CONSTRAINT uq_academy_path_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_learning_path_items (
                tenant_id uuid NOT NULL,
                path_id uuid NOT NULL,
                content_version_id uuid NOT NULL,
                ordinal integer NOT NULL,
                required boolean NOT NULL DEFAULT true,
                completion_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
                PRIMARY KEY (tenant_id, path_id, content_version_id),
                CONSTRAINT fk_academy_path_item_path
                    FOREIGN KEY (tenant_id, path_id)
                    REFERENCES academy_learning_paths(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_academy_path_item_version
                    FOREIGN KEY (tenant_id, content_version_id)
                    REFERENCES academy_content_versions(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT ck_academy_path_item_ordinal CHECK (ordinal > 0),
                CONSTRAINT uq_academy_path_item_ordinal UNIQUE (tenant_id, path_id, ordinal)
            )
            """,
            """
            CREATE TABLE academy_path_role_assignments (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                path_id uuid NOT NULL,
                role_key varchar(160) NOT NULL,
                required boolean NOT NULL DEFAULT true,
                due_days integer,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_path_role_path
                    FOREIGN KEY (tenant_id, path_id)
                    REFERENCES academy_learning_paths(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT ck_academy_role_due_days CHECK (due_days IS NULL OR due_days BETWEEN 0 AND 3650),
                CONSTRAINT uq_academy_path_role UNIQUE (tenant_id, path_id, role_key),
                CONSTRAINT uq_academy_path_role_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_enrollments (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                path_id uuid NOT NULL,
                subject varchar(255) NOT NULL,
                source varchar(20) NOT NULL DEFAULT 'role',
                status varchar(20) NOT NULL DEFAULT 'assigned',
                assigned_by varchar(255) NOT NULL,
                assigned_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                due_at timestamptz,
                started_at timestamptz,
                completed_at timestamptz,
                completion_revoked_at timestamptz,
                completion_revoked_by varchar(255),
                completion_revocation_reason varchar(500),
                CONSTRAINT fk_academy_enrollment_path
                    FOREIGN KEY (tenant_id, path_id)
                    REFERENCES academy_learning_paths(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT ck_academy_enrollment_source CHECK (source IN ('role', 'manual')),
                CONSTRAINT ck_academy_enrollment_status CHECK (status IN ('assigned', 'in_progress', 'completed', 'revoked')),
                CONSTRAINT uq_academy_enrollment_subject_path UNIQUE (tenant_id, subject, path_id),
                CONSTRAINT uq_academy_enrollment_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_progress (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                enrollment_id uuid NOT NULL,
                content_version_id uuid NOT NULL,
                subject varchar(255) NOT NULL,
                status varchar(20) NOT NULL DEFAULT 'not_started',
                progress_percent numeric(6,2) NOT NULL DEFAULT 0,
                last_position_ms bigint NOT NULL DEFAULT 0,
                max_position_ms bigint NOT NULL DEFAULT 0,
                watched_ms bigint NOT NULL DEFAULT 0,
                revision bigint NOT NULL DEFAULT 1,
                last_checkpoint_at timestamptz,
                completed_at timestamptz,
                updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_progress_enrollment
                    FOREIGN KEY (tenant_id, enrollment_id)
                    REFERENCES academy_enrollments(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_academy_progress_version
                    FOREIGN KEY (tenant_id, content_version_id)
                    REFERENCES academy_content_versions(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT ck_academy_progress_status CHECK (status IN ('not_started', 'in_progress', 'completed')),
                CONSTRAINT ck_academy_progress_percent CHECK (progress_percent BETWEEN 0 AND 100),
                CONSTRAINT ck_academy_progress_positions CHECK (last_position_ms >= 0 AND max_position_ms >= 0 AND watched_ms >= 0),
                CONSTRAINT ck_academy_progress_revision CHECK (revision > 0),
                CONSTRAINT uq_academy_progress UNIQUE (tenant_id, enrollment_id, content_version_id),
                CONSTRAINT uq_academy_progress_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_quizzes (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                content_version_id uuid NOT NULL,
                kind varchar(20) NOT NULL,
                checkpoint_at_ms bigint,
                pass_score numeric(6,2) NOT NULL DEFAULT 80,
                max_attempts integer,
                required boolean NOT NULL DEFAULT true,
                status varchar(20) NOT NULL DEFAULT 'draft',
                version_number integer NOT NULL DEFAULT 1,
                supersedes_quiz_id uuid,
                created_by varchar(255) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_quiz_version
                    FOREIGN KEY (tenant_id, content_version_id)
                    REFERENCES academy_content_versions(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_academy_quiz_supersedes
                    FOREIGN KEY (tenant_id, supersedes_quiz_id)
                    REFERENCES academy_quizzes(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT ck_academy_quiz_kind CHECK (kind IN ('checkpoint', 'completion')),
                CONSTRAINT ck_academy_quiz_status CHECK (status IN ('draft', 'published', 'retired')),
                CONSTRAINT ck_academy_quiz_score CHECK (pass_score BETWEEN 0 AND 100),
                CONSTRAINT ck_academy_quiz_attempt_limit CHECK (max_attempts IS NULL OR max_attempts > 0),
                CONSTRAINT ck_academy_quiz_version_number CHECK (version_number > 0),
                CONSTRAINT uq_academy_quiz_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_questions (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                quiz_id uuid NOT NULL,
                ordinal integer NOT NULL,
                question_type varchar(30) NOT NULL,
                prompt_i18n jsonb NOT NULL,
                points numeric(8,2) NOT NULL DEFAULT 1,
                required boolean NOT NULL DEFAULT true,
                CONSTRAINT fk_academy_question_quiz
                    FOREIGN KEY (tenant_id, quiz_id)
                    REFERENCES academy_quizzes(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT ck_academy_question_type CHECK (question_type IN ('single_choice', 'multiple_choice', 'true_false')),
                CONSTRAINT ck_academy_question_points CHECK (points > 0),
                CONSTRAINT uq_academy_question_ordinal UNIQUE (tenant_id, quiz_id, ordinal),
                CONSTRAINT uq_academy_question_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_question_options (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                question_id uuid NOT NULL,
                ordinal integer NOT NULL,
                label_i18n jsonb NOT NULL,
                is_correct boolean NOT NULL DEFAULT false,
                CONSTRAINT fk_academy_option_question
                    FOREIGN KEY (tenant_id, question_id)
                    REFERENCES academy_questions(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT uq_academy_option_ordinal UNIQUE (tenant_id, question_id, ordinal),
                CONSTRAINT uq_academy_option_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_quiz_attempts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                enrollment_id uuid NOT NULL,
                quiz_id uuid NOT NULL,
                subject varchar(255) NOT NULL,
                attempt_number integer NOT NULL,
                score numeric(6,2) NOT NULL,
                passed boolean NOT NULL,
                submitted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_attempt_enrollment
                    FOREIGN KEY (tenant_id, enrollment_id)
                    REFERENCES academy_enrollments(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_academy_attempt_quiz
                    FOREIGN KEY (tenant_id, quiz_id)
                    REFERENCES academy_quizzes(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT ck_academy_attempt_number CHECK (attempt_number > 0),
                CONSTRAINT ck_academy_attempt_score CHECK (score BETWEEN 0 AND 100),
                CONSTRAINT uq_academy_quiz_attempt_number UNIQUE (tenant_id, enrollment_id, quiz_id, subject, attempt_number),
                CONSTRAINT uq_academy_quiz_attempt_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_quiz_answers (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                attempt_id uuid NOT NULL,
                question_id uuid NOT NULL,
                selected_option_ids jsonb NOT NULL,
                is_correct boolean NOT NULL,
                awarded_points numeric(8,2) NOT NULL DEFAULT 0,
                CONSTRAINT fk_academy_answer_attempt
                    FOREIGN KEY (tenant_id, attempt_id)
                    REFERENCES academy_quiz_attempts(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_academy_answer_question
                    FOREIGN KEY (tenant_id, question_id)
                    REFERENCES academy_questions(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT uq_academy_answer_question UNIQUE (tenant_id, attempt_id, question_id),
                CONSTRAINT uq_academy_answer_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_certificates (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                enrollment_id uuid NOT NULL,
                path_id uuid NOT NULL,
                subject varchar(255) NOT NULL,
                certificate_code varchar(120) NOT NULL,
                contract_version varchar(80) NOT NULL,
                completion_fingerprint char(64) NOT NULL,
                issued_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at timestamptz,
                revoked_by varchar(255),
                revocation_reason varchar(500),
                CONSTRAINT fk_academy_certificate_enrollment
                    FOREIGN KEY (tenant_id, enrollment_id)
                    REFERENCES academy_enrollments(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT fk_academy_certificate_path
                    FOREIGN KEY (tenant_id, path_id)
                    REFERENCES academy_learning_paths(tenant_id, id)
                    ON DELETE RESTRICT,
                CONSTRAINT ck_academy_completion_fingerprint CHECK (completion_fingerprint ~ '^[0-9a-f]{64}$'),
                CONSTRAINT uq_academy_certificate_enrollment UNIQUE (tenant_id, enrollment_id),
                CONSTRAINT uq_academy_certificate_code UNIQUE (tenant_id, certificate_code),
                CONSTRAINT uq_academy_certificate_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_entitlements (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                resource_type varchar(20) NOT NULL,
                resource_id uuid NOT NULL,
                principal_type varchar(20) NOT NULL,
                principal_key varchar(255) NOT NULL,
                permission varchar(20) NOT NULL DEFAULT 'learn',
                starts_at timestamptz,
                ends_at timestamptz,
                created_by varchar(255) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_academy_entitlement_resource CHECK (resource_type IN ('content', 'path')),
                CONSTRAINT ck_academy_entitlement_principal CHECK (principal_type IN ('role', 'subject')),
                CONSTRAINT ck_academy_entitlement_permission CHECK (permission IN ('view', 'learn', 'manage')),
                CONSTRAINT ck_academy_entitlement_window CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at),
                CONSTRAINT uq_academy_entitlement UNIQUE (tenant_id, resource_type, resource_id, principal_type, principal_key, permission),
                CONSTRAINT uq_academy_entitlement_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_learning_events (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
                subject varchar(255) NOT NULL,
                actor_subject varchar(255) NOT NULL,
                event_type varchar(120) NOT NULL,
                enrollment_id uuid,
                content_version_id uuid,
                quiz_id uuid,
                idempotency_key varchar(160),
                request_id varchar(128) NOT NULL,
                data jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_academy_learning_event_idempotency UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key),
                CONSTRAINT uq_academy_learning_event_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_idempotency_keys (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                subject varchar(255) NOT NULL,
                operation varchar(120) NOT NULL,
                idempotency_key varchar(160) NOT NULL,
                resource_id varchar(255),
                request_fingerprint char(64) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_academy_request_fingerprint CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
                CONSTRAINT uq_academy_idempotency UNIQUE (tenant_id, subject, operation, idempotency_key),
                CONSTRAINT uq_academy_idempotency_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            """
            CREATE TABLE academy_document_chunks (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                content_version_id uuid NOT NULL,
                chunk_ordinal integer NOT NULL,
                locale varchar(5) NOT NULL,
                heading varchar(500),
                text_content text NOT NULL,
                source_page integer,
                source_anchor varchar(500),
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                search_vector tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(heading, '') || ' ' || text_content)
                ) STORED,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_academy_chunk_version
                    FOREIGN KEY (tenant_id, content_version_id)
                    REFERENCES academy_content_versions(tenant_id, id)
                    ON DELETE CASCADE,
                CONSTRAINT ck_academy_chunk_locale CHECK (locale IN ('tr', 'en', 'de', 'ar')),
                CONSTRAINT ck_academy_chunk_ordinal CHECK (chunk_ordinal > 0),
                CONSTRAINT ck_academy_chunk_text CHECK (length(text_content) BETWEEN 1 AND 20000),
                CONSTRAINT uq_academy_chunk_ordinal UNIQUE (tenant_id, content_version_id, chunk_ordinal),
                CONSTRAINT uq_academy_chunk_tenant_id UNIQUE (tenant_id, id)
            )
            """,
            "CREATE INDEX ix_academy_content_tenant_status ON academy_content_items (tenant_id, status, content_type)",
            "CREATE INDEX ix_academy_content_version_tenant_status ON academy_content_versions (tenant_id, status, content_id)",
            "CREATE INDEX ix_academy_media_content_version ON academy_media_assets (tenant_id, content_version_id, transcode_status)",
            "CREATE INDEX ix_academy_enrollment_subject_status ON academy_enrollments (tenant_id, subject, status)",
            "CREATE INDEX ix_academy_progress_subject ON academy_progress (tenant_id, subject, updated_at DESC)",
            "CREATE INDEX ix_academy_quiz_content_version ON academy_quizzes (tenant_id, content_version_id, status, checkpoint_at_ms)",
            "CREATE INDEX ix_academy_learning_events_subject_created ON academy_learning_events (tenant_id, subject, created_at DESC)",
            "CREATE INDEX ix_academy_document_chunks_search ON academy_document_chunks USING gin (search_vector)",
        )
    )

    for table_name in ACADEMY_TABLES:
        _tenant_policy(table_name)

    op.execute(
        """
        CREATE FUNCTION prevent_academy_learning_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            RAISE EXCEPTION 'academy_learning_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER academy_learning_events_append_only
        BEFORE UPDATE OR DELETE ON academy_learning_events
        FOR EACH ROW EXECUTE FUNCTION prevent_academy_learning_event_mutation()
        """
    )

    read_write_tables = (
        "academy_content_items",
        "academy_content_versions",
        "academy_media_assets",
        "academy_learning_paths",
        "academy_learning_path_items",
        "academy_path_role_assignments",
        "academy_enrollments",
        "academy_progress",
        "academy_quizzes",
        "academy_questions",
        "academy_question_options",
        "academy_quiz_attempts",
        "academy_quiz_answers",
        "academy_certificates",
        "academy_entitlements",
        "academy_idempotency_keys",
        "academy_document_chunks",
    )
    op.execute(f"GRANT SELECT, INSERT ON TABLE {', '.join(read_write_tables)} TO {RUNTIME_ROLE}")
    op.execute(
        f"GRANT UPDATE ON TABLE academy_enrollments, academy_progress, academy_certificates TO {RUNTIME_ROLE}"
    )
    op.execute(f"GRANT SELECT, INSERT ON TABLE academy_learning_events TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS academy_learning_events_append_only ON academy_learning_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_academy_learning_event_mutation()")
    for table_name in reversed(ACADEMY_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
