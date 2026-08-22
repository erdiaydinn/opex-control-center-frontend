"""Add Academy operational closed-loop readiness authority.

Revision ID: 0060_academy_operational_readiness
Revises: 0059_audit_inference_lease_immutability
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0060_academy_operational_readiness"
down_revision: str | None = "0059_audit_inference_lease_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
TABLES = (
    "academy_operational_signal_mappings",
    "academy_operational_signal_mapping_retirements",
    "academy_operational_signal_events",
    "academy_operational_remediations",
    "academy_operational_outcome_observations",
)


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def _append_only(table_name: str) -> None:
    op.execute(
        f"""CREATE OR REPLACE FUNCTION {table_name}_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '{table_name} is append-only';
        END;
        $$"""
    )
    op.execute(
        f"CREATE TRIGGER trg_{table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name} "
        f"FOR EACH ROW EXECUTE FUNCTION {table_name}_append_only()"
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE academy_operational_signal_mappings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_subject varchar(255) NOT NULL,
            source_domain varchar(40) NOT NULL,
            signal_type varchar(160) NOT NULL,
            skill_id uuid NOT NULL,
            required_level smallint NOT NULL,
            recommended_path_id uuid NOT NULL,
            minimum_severity smallint NOT NULL DEFAULT 1,
            metric_key varchar(160) NOT NULL,
            metric_direction varchar(20) NOT NULL,
            mapping_version integer NOT NULL DEFAULT 1,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_operational_mapping_skill
                FOREIGN KEY (tenant_id, skill_id)
                REFERENCES academy_skills(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_academy_operational_mapping_path
                FOREIGN KEY (tenant_id, recommended_path_id)
                REFERENCES academy_learning_paths(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_academy_operational_mapping_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_academy_operational_mapping_version UNIQUE (
                tenant_id, source_subject, source_domain, signal_type, skill_id, mapping_version
            ),
            CONSTRAINT ck_academy_operational_mapping_domain CHECK (
                source_domain IN ('audit','inventory','dockos','planogram','workforce',
                                  'field_intelligence','fraud','safety')
            ),
            CONSTRAINT ck_academy_operational_mapping_level CHECK (required_level BETWEEN 1 AND 5),
            CONSTRAINT ck_academy_operational_mapping_severity CHECK (minimum_severity BETWEEN 1 AND 5),
            CONSTRAINT ck_academy_operational_mapping_version CHECK (mapping_version > 0),
            CONSTRAINT ck_academy_operational_metric_direction CHECK (
                metric_direction IN ('higher_better','lower_better')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_operational_mapping_lookup ON academy_operational_signal_mappings "
        "(tenant_id, source_subject, source_domain, signal_type, minimum_severity)"
    )

    op.execute(
        """
        CREATE TABLE academy_operational_signal_mapping_retirements (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            mapping_id uuid NOT NULL,
            reason varchar(500) NOT NULL,
            retired_by varchar(255) NOT NULL,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_operational_mapping_retirement
                FOREIGN KEY (tenant_id, mapping_id)
                REFERENCES academy_operational_signal_mappings(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_academy_operational_mapping_retirement UNIQUE (tenant_id, mapping_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE academy_operational_signal_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_subject varchar(255) NOT NULL,
            source_domain varchar(40) NOT NULL,
            signal_type varchar(160) NOT NULL,
            subject varchar(255) NOT NULL,
            severity smallint NOT NULL,
            source_ref varchar(255) NOT NULL,
            source_version varchar(120) NOT NULL,
            source_fingerprint char(64) NOT NULL,
            occurred_at timestamptz NOT NULL,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_academy_operational_signal_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_academy_operational_signal_source UNIQUE (
                tenant_id, source_domain, source_ref, source_version
            ),
            CONSTRAINT ck_academy_operational_signal_domain CHECK (
                source_domain IN ('audit','inventory','dockos','planogram','workforce',
                                  'field_intelligence','fraud','safety')
            ),
            CONSTRAINT ck_academy_operational_signal_severity CHECK (severity BETWEEN 1 AND 5),
            CONSTRAINT ck_academy_operational_signal_fingerprint CHECK (
                source_fingerprint ~ '^[0-9a-f]{64}$'
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_operational_signal_subject ON academy_operational_signal_events "
        "(tenant_id, subject, occurred_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE academy_operational_remediations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            signal_event_id uuid NOT NULL,
            mapping_id uuid NOT NULL,
            subject varchar(255) NOT NULL,
            skill_id uuid NOT NULL,
            current_level smallint NOT NULL,
            required_level smallint NOT NULL,
            recommended_path_id uuid NOT NULL,
            policy_version varchar(80) NOT NULL DEFAULT 'operational_gap_v1',
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_operational_remediation_signal
                FOREIGN KEY (tenant_id, signal_event_id)
                REFERENCES academy_operational_signal_events(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_academy_operational_remediation_mapping
                FOREIGN KEY (tenant_id, mapping_id)
                REFERENCES academy_operational_signal_mappings(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_academy_operational_remediation_skill
                FOREIGN KEY (tenant_id, skill_id)
                REFERENCES academy_skills(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_academy_operational_remediation_path
                FOREIGN KEY (tenant_id, recommended_path_id)
                REFERENCES academy_learning_paths(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_academy_operational_remediation_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_academy_operational_remediation_signal_mapping UNIQUE (
                tenant_id, signal_event_id, mapping_id
            ),
            CONSTRAINT ck_academy_operational_remediation_current CHECK (current_level BETWEEN 0 AND 5),
            CONSTRAINT ck_academy_operational_remediation_required CHECK (required_level BETWEEN 1 AND 5),
            CONSTRAINT ck_academy_operational_remediation_gap CHECK (current_level < required_level)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_operational_remediation_subject ON academy_operational_remediations "
        "(tenant_id, subject, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE academy_operational_outcome_observations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            remediation_id uuid NOT NULL,
            source_subject varchar(255) NOT NULL,
            source_domain varchar(40) NOT NULL,
            source_ref varchar(255) NOT NULL,
            source_version varchar(120) NOT NULL,
            source_fingerprint char(64) NOT NULL,
            metric_key varchar(160) NOT NULL,
            metric_direction varchar(20) NOT NULL,
            baseline_value numeric(20,6) NOT NULL,
            observed_value numeric(20,6) NOT NULL,
            window_start timestamptz NOT NULL,
            window_end timestamptz NOT NULL,
            observed_at timestamptz NOT NULL,
            recorded_by varchar(255) NOT NULL,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_operational_observation_remediation
                FOREIGN KEY (tenant_id, remediation_id)
                REFERENCES academy_operational_remediations(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_academy_operational_observation_source UNIQUE (
                tenant_id, remediation_id, source_ref, source_version
            ),
            CONSTRAINT ck_academy_operational_observation_domain CHECK (
                source_domain IN ('audit','inventory','dockos','planogram','workforce',
                                  'field_intelligence','fraud','safety')
            ),
            CONSTRAINT ck_academy_operational_observation_fingerprint CHECK (
                source_fingerprint ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_academy_operational_observation_direction CHECK (
                metric_direction IN ('higher_better','lower_better')
            ),
            CONSTRAINT ck_academy_operational_observation_window CHECK (window_end >= window_start)
        )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION academy_validate_operational_mapping()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE skill_status varchar(20); path_status varchar(20);
        BEGIN
            SELECT status INTO skill_status FROM academy_skills
             WHERE tenant_id=NEW.tenant_id AND id=NEW.skill_id;
            SELECT status INTO path_status FROM academy_learning_paths
             WHERE tenant_id=NEW.tenant_id AND id=NEW.recommended_path_id;
            IF skill_status IS DISTINCT FROM 'active' THEN
                RAISE EXCEPTION 'Operational mapping requires active Academy skill';
            END IF;
            IF path_status IS DISTINCT FROM 'published' THEN
                RAISE EXCEPTION 'Operational mapping requires published Academy path';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_academy_validate_operational_mapping BEFORE INSERT ON "
        "academy_operational_signal_mappings FOR EACH ROW EXECUTE FUNCTION "
        "academy_validate_operational_mapping()"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION academy_validate_operational_remediation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE ev record; mp record;
        BEGIN
            SELECT * INTO ev FROM academy_operational_signal_events
             WHERE tenant_id=NEW.tenant_id AND id=NEW.signal_event_id;
            SELECT * INTO mp FROM academy_operational_signal_mappings
             WHERE tenant_id=NEW.tenant_id AND id=NEW.mapping_id;
            IF ev.id IS NULL OR mp.id IS NULL
               OR ev.subject IS DISTINCT FROM NEW.subject
               OR ev.source_subject IS DISTINCT FROM mp.source_subject
               OR ev.source_domain IS DISTINCT FROM mp.source_domain
               OR ev.signal_type IS DISTINCT FROM mp.signal_type
               OR ev.severity < mp.minimum_severity
               OR NEW.skill_id IS DISTINCT FROM mp.skill_id
               OR NEW.required_level IS DISTINCT FROM mp.required_level
               OR NEW.recommended_path_id IS DISTINCT FROM mp.recommended_path_id
               OR NEW.current_level >= NEW.required_level THEN
                RAISE EXCEPTION 'Operational remediation authority mismatch';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_academy_validate_operational_remediation BEFORE INSERT ON "
        "academy_operational_remediations FOR EACH ROW EXECUTE FUNCTION "
        "academy_validate_operational_remediation()"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION academy_validate_operational_observation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE ev record; mp record;
        BEGIN
            SELECT event.*, mapping.metric_key, mapping.metric_direction, mapping.source_subject AS mapping_subject
              INTO ev
              FROM academy_operational_remediations remediation
              JOIN academy_operational_signal_events event
                ON event.tenant_id=remediation.tenant_id AND event.id=remediation.signal_event_id
              JOIN academy_operational_signal_mappings mapping
                ON mapping.tenant_id=remediation.tenant_id AND mapping.id=remediation.mapping_id
             WHERE remediation.tenant_id=NEW.tenant_id AND remediation.id=NEW.remediation_id;
            IF ev.id IS NULL
               OR NEW.source_subject IS DISTINCT FROM ev.mapping_subject
               OR NEW.recorded_by IS DISTINCT FROM ev.mapping_subject
               OR NEW.source_domain IS DISTINCT FROM ev.source_domain
               OR NEW.metric_key IS DISTINCT FROM ev.metric_key
               OR NEW.metric_direction IS DISTINCT FROM ev.metric_direction THEN
                RAISE EXCEPTION 'Operational outcome source authority mismatch';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_academy_validate_operational_observation BEFORE INSERT ON "
        "academy_operational_outcome_observations FOR EACH ROW EXECUTE FUNCTION "
        "academy_validate_operational_observation()"
    )

    op.execute(
        """
        CREATE VIEW academy_operational_readiness_authority
        WITH (security_invoker = true) AS
        SELECT
            remediation.tenant_id,
            remediation.id AS remediation_id,
            remediation.subject,
            event.id AS signal_event_id,
            event.source_domain,
            event.signal_type,
            event.source_ref,
            event.source_version,
            event.source_fingerprint,
            event.severity,
            event.occurred_at,
            skill.skill_key,
            skill.title_i18n AS skill_title_i18n,
            remediation.current_level,
            remediation.required_level,
            (remediation.required_level-remediation.current_level)::integer AS gap,
            path.id AS recommended_path_id,
            path.key AS recommended_path_key,
            path.title_i18n AS recommended_path_title_i18n,
            enrollment.id AS enrollment_id,
            enrollment.status AS enrollment_status,
            observation.id AS latest_observation_id,
            observation.metric_key,
            observation.metric_direction,
            observation.baseline_value,
            observation.observed_value,
            CASE WHEN observation.id IS NULL THEN NULL
                 ELSE observation.observed_value-observation.baseline_value END AS observed_delta,
            observation.window_start,
            observation.window_end,
            observation.observed_at,
            FALSE AS causal_attribution,
            remediation.policy_version,
            remediation.created_at
        FROM academy_operational_remediations remediation
        JOIN academy_operational_signal_events event
          ON event.tenant_id=remediation.tenant_id AND event.id=remediation.signal_event_id
        JOIN academy_skills skill
          ON skill.tenant_id=remediation.tenant_id AND skill.id=remediation.skill_id
        JOIN academy_learning_paths path
          ON path.tenant_id=remediation.tenant_id AND path.id=remediation.recommended_path_id
        LEFT JOIN LATERAL (
            SELECT id, status FROM academy_enrollments e
             WHERE e.tenant_id=remediation.tenant_id
               AND e.subject=remediation.subject
               AND e.path_id=remediation.recommended_path_id
             ORDER BY e.assigned_at DESC, e.id DESC LIMIT 1
        ) enrollment ON TRUE
        LEFT JOIN LATERAL (
            SELECT o.* FROM academy_operational_outcome_observations o
             WHERE o.tenant_id=remediation.tenant_id AND o.remediation_id=remediation.id
             ORDER BY o.observed_at DESC, o.id DESC LIMIT 1
        ) observation ON TRUE
        """
    )

    for table_name in TABLES:
        _tenant_policy(table_name)
        _append_only(table_name)

    op.execute(f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {RUNTIME_ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE ON {', '.join(TABLES)} FROM {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT ON academy_operational_readiness_authority TO {RUNTIME_ROLE}")

    op.execute(
        """
        WITH desired(role_key, permission_key) AS (
            VALUES
            ('academy_learner','feature:academy:operationalReadiness'),
            ('academy_instructor','feature:academy:operationalReadiness'),
            ('academy_admin','feature:academy:operationalReadiness'),
            ('academy_admin','action:academy:manageOperationalReadiness'),
            ('super_admin','feature:academy:operationalReadiness'),
            ('super_admin','action:academy:manageOperationalReadiness'),
            ('super_admin','action:academy:ingestOperationalSignals'),
            ('super_admin','action:academy:recordOperationalOutcomes')
        )
        INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
        SELECT roles.tenant_id, roles.id, desired.permission_key, '{"type":"all"}'::jsonb
          FROM roles JOIN desired ON desired.role_key=roles.key
         WHERE roles.is_system=true
        ON CONFLICT (tenant_id, role_id, permission_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS academy_operational_readiness_authority")
    for table_name in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute(f"DROP FUNCTION IF EXISTS {table_name}_append_only()")
    op.execute("DROP TRIGGER IF EXISTS trg_academy_validate_operational_observation ON academy_operational_outcome_observations")
    op.execute("DROP FUNCTION IF EXISTS academy_validate_operational_observation()")
    op.execute("DROP TRIGGER IF EXISTS trg_academy_validate_operational_remediation ON academy_operational_remediations")
    op.execute("DROP FUNCTION IF EXISTS academy_validate_operational_remediation()")
    op.execute("DROP TRIGGER IF EXISTS trg_academy_validate_operational_mapping ON academy_operational_signal_mappings")
    op.execute("DROP FUNCTION IF EXISTS academy_validate_operational_mapping()")
    for table_name in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table_name}"')
