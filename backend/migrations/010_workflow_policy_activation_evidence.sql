-- EAY Workflow Policy activation evidence gate.
-- Reuses workflow_policy_current_tenant() from migration 009; no parallel tenant authority.
BEGIN;

CREATE TABLE IF NOT EXISTS workflow_policy_simulation_reviews (
  tenant_id text NOT NULL,
  simulation_review_id uuid NOT NULL,
  workflow_id text NOT NULL,
  baseline_version integer NOT NULL CHECK (baseline_version > 0),
  candidate_version integer NOT NULL CHECK (candidate_version > 0),
  impact_fingerprint text NOT NULL CHECK (impact_fingerprint ~ '^[0-9a-f]{64}$'),
  simulated_event_count integer NOT NULL CHECK (simulated_event_count > 0),
  changed_event_count integer NOT NULL CHECK (changed_event_count >= 0),
  high_risk_changed_events integer NOT NULL CHECK (high_risk_changed_events >= 0),
  high_risk_acknowledged boolean NOT NULL DEFAULT false,
  reviewed_by text NOT NULL,
  reviewed_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, simulation_review_id),
  UNIQUE (tenant_id, workflow_id, candidate_version, impact_fingerprint),
  FOREIGN KEY (tenant_id, workflow_id, baseline_version)
    REFERENCES workflow_policy_definitions(tenant_id, workflow_id, version) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, workflow_id, candidate_version)
    REFERENCES workflow_policy_definitions(tenant_id, workflow_id, version) ON DELETE RESTRICT,
  CHECK (candidate_version = baseline_version + 1),
  CHECK (changed_event_count <= simulated_event_count),
  CHECK (high_risk_changed_events <= changed_event_count),
  CHECK (high_risk_changed_events = 0 OR high_risk_acknowledged IS TRUE)
);
CREATE INDEX IF NOT EXISTS workflow_policy_simulation_reviews_candidate_idx
  ON workflow_policy_simulation_reviews (tenant_id, workflow_id, candidate_version, reviewed_at DESC);

DROP TRIGGER IF EXISTS workflow_policy_simulation_reviews_immutable ON workflow_policy_simulation_reviews;
CREATE TRIGGER workflow_policy_simulation_reviews_immutable
BEFORE UPDATE OR DELETE ON workflow_policy_simulation_reviews
FOR EACH ROW EXECUTE FUNCTION workflow_policy_immutable_row();

ALTER TABLE workflow_policy_simulation_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_policy_simulation_reviews FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workflow_policy_simulation_reviews_tenant ON workflow_policy_simulation_reviews;
CREATE POLICY workflow_policy_simulation_reviews_tenant
ON workflow_policy_simulation_reviews
USING (tenant_id=workflow_policy_current_tenant())
WITH CHECK (tenant_id=workflow_policy_current_tenant());

CREATE OR REPLACE FUNCTION workflow_policy_validate_governance_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  current_status text;
  last_occurred_at timestamptz;
  definition_created_at timestamptz;
  definition_created_by text;
  activation_review_count integer;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(NEW.tenant_id || '|' || NEW.workflow_id || '|' || NEW.workflow_version::text));

  SELECT created_at, created_by
    INTO definition_created_at, definition_created_by
  FROM workflow_policy_definitions
  WHERE tenant_id=NEW.tenant_id
    AND workflow_id=NEW.workflow_id
    AND version=NEW.workflow_version;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'workflow definition not found for governance event';
  END IF;

  SELECT to_status, occurred_at
    INTO current_status, last_occurred_at
  FROM workflow_policy_governance_events
  WHERE tenant_id=NEW.tenant_id
    AND workflow_id=NEW.workflow_id
    AND workflow_version=NEW.workflow_version
  ORDER BY occurred_at DESC, governance_event_id DESC
  LIMIT 1;

  current_status := coalesce(current_status, 'draft');
  IF NEW.from_status <> current_status THEN
    RAISE EXCEPTION 'workflow governance from_status % does not match current status %', NEW.from_status, current_status;
  END IF;
  IF NEW.occurred_at < definition_created_at THEN
    RAISE EXCEPTION 'workflow governance event cannot predate workflow definition';
  END IF;
  IF last_occurred_at IS NOT NULL AND NEW.occurred_at <= last_occurred_at THEN
    RAISE EXCEPTION 'workflow governance timestamps must advance monotonically';
  END IF;
  IF NEW.from_status='draft' AND NEW.to_status='approved' AND NEW.actor_id=definition_created_by THEN
    RAISE EXCEPTION 'workflow author cannot approve own workflow version';
  END IF;

  IF NEW.from_status='approved' AND NEW.to_status='effective' THEN
    SELECT count(*)
      INTO activation_review_count
    FROM workflow_policy_simulation_reviews r
    WHERE r.tenant_id=NEW.tenant_id
      AND r.workflow_id=NEW.workflow_id
      AND r.candidate_version=NEW.workflow_version
      AND r.reviewed_at >= last_occurred_at
      AND r.reviewed_at <= NEW.occurred_at
      AND (r.high_risk_changed_events=0 OR r.high_risk_acknowledged IS TRUE);

    IF activation_review_count < 1 THEN
      RAISE EXCEPTION 'workflow activation requires reviewed simulation evidence after approval';
    END IF;
  END IF;

  RETURN NEW;
END $$;

INSERT INTO workflow_policy_schema_migrations(version,name)
VALUES (10,'workflow policy simulation review and activation evidence gate')
ON CONFLICT (version) DO NOTHING;
COMMIT;
