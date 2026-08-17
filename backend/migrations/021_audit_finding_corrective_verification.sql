-- Item 24: immutable Audit finding -> corrective action -> verification lifecycle.
BEGIN;

CREATE TABLE IF NOT EXISTS audit_findings (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  finding_id uuid NOT NULL DEFAULT gen_random_uuid(),
  audit_run_id uuid NOT NULL,
  audit_snapshot_hash text NOT NULL CHECK (audit_snapshot_hash ~ '^[0-9a-f]{64}$'),
  template_key text NOT NULL CHECK (btrim(template_key) <> ''),
  template_revision integer NOT NULL CHECK (template_revision > 0),
  template_hash text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
  question_id text NOT NULL CHECK (btrim(question_id) <> ''),
  severity text NOT NULL CHECK (severity IN ('critical','high','medium','low','observation')),
  title text NOT NULL CHECK (btrim(title) <> ''),
  description text NOT NULL CHECK (btrim(description) <> ''),
  opened_by text NOT NULL CHECK (btrim(opened_by) <> ''),
  opened_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, finding_id),
  FOREIGN KEY (tenant_id, audit_run_id)
    REFERENCES audit_run_snapshots(tenant_id, audit_run_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_corrective_actions (
  tenant_id text NOT NULL,
  finding_id uuid NOT NULL,
  action_id uuid NOT NULL DEFAULT gen_random_uuid(),
  owner_subject text NOT NULL CHECK (btrim(owner_subject) <> ''),
  description text NOT NULL CHECK (btrim(description) <> ''),
  due_at timestamptz NOT NULL,
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, finding_id, action_id),
  FOREIGN KEY (tenant_id, finding_id)
    REFERENCES audit_findings(tenant_id, finding_id) ON DELETE RESTRICT,
  CHECK (due_at > created_at)
);

CREATE TABLE IF NOT EXISTS audit_corrective_evidence (
  tenant_id text NOT NULL,
  finding_id uuid NOT NULL,
  action_id uuid NOT NULL,
  evidence_id uuid NOT NULL DEFAULT gen_random_uuid(),
  evidence_ref text NOT NULL CHECK (btrim(evidence_ref) <> ''),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(provenance)='object'),
  attached_by text NOT NULL CHECK (btrim(attached_by) <> ''),
  attached_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, finding_id, action_id, evidence_id),
  FOREIGN KEY (tenant_id, finding_id, action_id)
    REFERENCES audit_corrective_actions(tenant_id, finding_id, action_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_finding_verifications (
  tenant_id text NOT NULL,
  finding_id uuid NOT NULL,
  action_id uuid NOT NULL,
  verification_id uuid NOT NULL DEFAULT gen_random_uuid(),
  verifier_subject text NOT NULL CHECK (btrim(verifier_subject) <> ''),
  outcome text NOT NULL CHECK (outcome IN ('passed','failed')),
  rationale text NOT NULL CHECK (btrim(rationale) <> ''),
  verified_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, finding_id, action_id, verification_id),
  FOREIGN KEY (tenant_id, finding_id, action_id)
    REFERENCES audit_corrective_actions(tenant_id, finding_id, action_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_finding_reopens (
  tenant_id text NOT NULL,
  finding_id uuid NOT NULL,
  reopen_id uuid NOT NULL DEFAULT gen_random_uuid(),
  reopened_by text NOT NULL CHECK (btrim(reopened_by) <> ''),
  reason text NOT NULL CHECK (btrim(reason) <> ''),
  reopened_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, finding_id, reopen_id),
  FOREIGN KEY (tenant_id, finding_id)
    REFERENCES audit_findings(tenant_id, finding_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS audit_findings_run_idx
  ON audit_findings(tenant_id, audit_run_id, opened_at DESC);
CREATE INDEX IF NOT EXISTS audit_actions_finding_idx
  ON audit_corrective_actions(tenant_id, finding_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_verifications_finding_idx
  ON audit_finding_verifications(tenant_id, finding_id, verified_at DESC);
CREATE INDEX IF NOT EXISTS audit_reopens_finding_idx
  ON audit_finding_reopens(tenant_id, finding_id, reopened_at DESC);

CREATE OR REPLACE FUNCTION audit_history_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END $$;

CREATE OR REPLACE FUNCTION audit_finding_source_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  run_row audit_run_snapshots%ROWTYPE;
  visible_match boolean;
BEGIN
  SELECT * INTO run_row
  FROM audit_run_snapshots
  WHERE tenant_id=NEW.tenant_id AND audit_run_id=NEW.audit_run_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'finding must reference an exact tenant audit run';
  END IF;
  IF NEW.audit_snapshot_hash IS DISTINCT FROM run_row.snapshot_hash
     OR NEW.template_key IS DISTINCT FROM run_row.template_key
     OR NEW.template_revision IS DISTINCT FROM run_row.template_revision
     OR NEW.template_hash IS DISTINCT FROM run_row.template_hash THEN
    RAISE EXCEPTION 'finding audit provenance does not match exact run snapshot';
  END IF;

  SELECT EXISTS (
    SELECT 1 FROM jsonb_array_elements_text(run_row.visible_question_ids) AS q(value)
    WHERE q.value=NEW.question_id
  ) INTO visible_match;
  IF NOT visible_match THEN
    RAISE EXCEPTION 'finding question must be visible in exact audit run snapshot';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS audit_finding_source_guard_trigger ON audit_findings;
CREATE TRIGGER audit_finding_source_guard_trigger
BEFORE INSERT ON audit_findings
FOR EACH ROW EXECUTE FUNCTION audit_finding_source_guard();

CREATE OR REPLACE FUNCTION audit_action_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  latest_outcome text;
  latest_verified_at timestamptz;
  latest_reopened_at timestamptz;
BEGIN
  SELECT outcome, verified_at INTO latest_outcome, latest_verified_at
  FROM audit_finding_verifications
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id
  ORDER BY verified_at DESC, verification_id DESC
  LIMIT 1;

  SELECT max(reopened_at) INTO latest_reopened_at
  FROM audit_finding_reopens
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id;

  IF latest_outcome='passed'
     AND (latest_reopened_at IS NULL OR latest_reopened_at < latest_verified_at) THEN
    RAISE EXCEPTION 'closed finding must be explicitly reopened before a new corrective action';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS audit_action_guard_trigger ON audit_corrective_actions;
CREATE TRIGGER audit_action_guard_trigger
BEFORE INSERT ON audit_corrective_actions
FOR EACH ROW EXECUTE FUNCTION audit_action_guard();

CREATE OR REPLACE FUNCTION audit_verification_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  action_owner text;
  action_created_at timestamptz;
  latest_action_id uuid;
  latest_outcome text;
  latest_verified_at timestamptz;
  latest_reopened_at timestamptz;
  evidence_count integer;
BEGIN
  SELECT owner_subject, created_at INTO action_owner, action_created_at
  FROM audit_corrective_actions
  WHERE tenant_id=NEW.tenant_id
    AND finding_id=NEW.finding_id
    AND action_id=NEW.action_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'verification action is not part of finding';
  END IF;
  IF NEW.verifier_subject=action_owner THEN
    RAISE EXCEPTION 'corrective action owner cannot verify own action';
  END IF;
  IF NEW.verified_at <= action_created_at THEN
    RAISE EXCEPTION 'verification must occur after corrective action creation';
  END IF;

  SELECT action_id INTO latest_action_id
  FROM audit_corrective_actions
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id
  ORDER BY created_at DESC, action_id DESC
  LIMIT 1;
  IF latest_action_id IS DISTINCT FROM NEW.action_id THEN
    RAISE EXCEPTION 'verification must target latest corrective action';
  END IF;

  SELECT outcome, verified_at INTO latest_outcome, latest_verified_at
  FROM audit_finding_verifications
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id
  ORDER BY verified_at DESC, verification_id DESC
  LIMIT 1;
  SELECT max(reopened_at) INTO latest_reopened_at
  FROM audit_finding_reopens
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id;
  IF latest_outcome='passed'
     AND (latest_reopened_at IS NULL OR latest_reopened_at < latest_verified_at) THEN
    RAISE EXCEPTION 'closed finding must be reopened before another verification';
  END IF;

  IF NEW.outcome='passed' THEN
    SELECT count(*) INTO evidence_count
    FROM audit_corrective_evidence
    WHERE tenant_id=NEW.tenant_id
      AND finding_id=NEW.finding_id
      AND action_id=NEW.action_id
      AND attached_at <= NEW.verified_at;
    IF evidence_count=0 THEN
      RAISE EXCEPTION 'passed verification requires corrective evidence';
    END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS audit_verification_guard_trigger ON audit_finding_verifications;
CREATE TRIGGER audit_verification_guard_trigger
BEFORE INSERT ON audit_finding_verifications
FOR EACH ROW EXECUTE FUNCTION audit_verification_guard();

CREATE OR REPLACE FUNCTION audit_reopen_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  latest_outcome text;
  latest_verified_at timestamptz;
  latest_reopened_at timestamptz;
BEGIN
  SELECT outcome, verified_at INTO latest_outcome, latest_verified_at
  FROM audit_finding_verifications
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id
  ORDER BY verified_at DESC, verification_id DESC
  LIMIT 1;
  IF latest_outcome IS DISTINCT FROM 'passed' THEN
    RAISE EXCEPTION 'only a successfully verified closed finding can be reopened';
  END IF;
  IF NEW.reopened_at <= latest_verified_at THEN
    RAISE EXCEPTION 'reopen must occur after closing verification';
  END IF;
  SELECT max(reopened_at) INTO latest_reopened_at
  FROM audit_finding_reopens
  WHERE tenant_id=NEW.tenant_id AND finding_id=NEW.finding_id;
  IF latest_reopened_at IS NOT NULL AND latest_reopened_at >= latest_verified_at THEN
    RAISE EXCEPTION 'finding is already reopened';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS audit_reopen_guard_trigger ON audit_finding_reopens;
CREATE TRIGGER audit_reopen_guard_trigger
BEFORE INSERT ON audit_finding_reopens
FOR EACH ROW EXECUTE FUNCTION audit_reopen_guard();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'audit_findings',
    'audit_corrective_actions',
    'audit_corrective_evidence',
    'audit_finding_verifications',
    'audit_finding_reopens'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', table_name || '_immutable', table_name);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION audit_history_immutable()',
      table_name || '_immutable',
      table_name
    );
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=audit_current_tenant()) WITH CHECK (tenant_id=audit_current_tenant())',
      table_name || '_tenant',
      table_name
    );
  END LOOP;
END $$;

CREATE OR REPLACE VIEW audit_finding_state
WITH (security_invoker=true) AS
SELECT
  f.tenant_id,
  f.finding_id,
  f.audit_run_id,
  f.question_id,
  f.severity,
  f.title,
  CASE
    WHEN p.passed_at IS NOT NULL
      AND (restart.restart_at IS NULL OR p.passed_at > restart.restart_at)
      THEN 'closed'
    WHEN a.action_id IS NULL
      THEN CASE WHEN restart.restart_at IS NULL THEN 'open' ELSE 'reopened' END
    WHEN restart.restart_at IS NOT NULL AND a.created_at <= restart.restart_at
      THEN 'reopened'
    WHEN e.has_evidence THEN 'ready_for_verification'
    ELSE 'action_in_progress'
  END AS state
FROM audit_findings f
LEFT JOIN LATERAL (
  SELECT action_id, created_at
  FROM audit_corrective_actions a0
  WHERE a0.tenant_id=f.tenant_id AND a0.finding_id=f.finding_id
  ORDER BY created_at DESC, action_id DESC LIMIT 1
) a ON true
LEFT JOIN LATERAL (
  SELECT true AS has_evidence
  FROM audit_corrective_evidence e0
  WHERE e0.tenant_id=f.tenant_id
    AND e0.finding_id=f.finding_id
    AND e0.action_id=a.action_id
  LIMIT 1
) e ON true
LEFT JOIN LATERAL (
  SELECT max(verified_at) AS passed_at
  FROM audit_finding_verifications v0
  WHERE v0.tenant_id=f.tenant_id
    AND v0.finding_id=f.finding_id
    AND v0.outcome='passed'
) p ON true
LEFT JOIN LATERAL (
  SELECT max(verified_at) AS failed_at
  FROM audit_finding_verifications v0
  WHERE v0.tenant_id=f.tenant_id
    AND v0.finding_id=f.finding_id
    AND v0.outcome='failed'
) vf ON true
LEFT JOIN LATERAL (
  SELECT max(reopened_at) AS explicit_reopen_at
  FROM audit_finding_reopens r0
  WHERE r0.tenant_id=f.tenant_id AND r0.finding_id=f.finding_id
) r ON true
LEFT JOIN LATERAL (
  SELECT GREATEST(vf.failed_at, r.explicit_reopen_at) AS restart_at
) restart ON true;

COMMIT;
