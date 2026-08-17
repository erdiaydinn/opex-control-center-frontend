-- Workforce V35 / roadmap 13/60: Demand Pressure Index and root-cause authority.
--
-- DPI snapshots bind exact governed demand and capacity fingerprints. Bad KPIs
-- are evidence, not staffing authority. Classifier output is immutable and
-- cannot directly authorize additional people.

CREATE TABLE IF NOT EXISTS workforce_dpi_snapshots (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  interval_start timestamptz NOT NULL,
  model_version text NOT NULL,
  demand_snapshot_fingerprint char(64) NOT NULL,
  capacity_snapshot_fingerprint char(64) NOT NULL,
  required_man_hours numeric(24,10) NOT NULL,
  effective_man_hours numeric(24,10) NOT NULL,
  skill_deficit_man_hours numeric(24,10) NOT NULL,
  demand_pressure_index numeric(24,10) NOT NULL,
  capacity_gap_man_hours numeric(24,10) NOT NULL,
  capacity_sufficient boolean NOT NULL,
  kpi_bad boolean NOT NULL,
  bad_kpi_keys jsonb NOT NULL,
  manpower_shortage boolean NOT NULL,
  root_cause text NOT NULL,
  automatic_extra_people_permitted boolean NOT NULL DEFAULT FALSE,
  staffing_review_required boolean NOT NULL,
  kpi_observations jsonb NOT NULL,
  explanation jsonb NOT NULL,
  input_fingerprint char(64) NOT NULL,
  snapshot_fingerprint char(64) NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, snapshot_fingerprint),
  CHECK (length(trim(location_id)) > 0),
  CHECK (length(trim(model_version)) > 0),
  CHECK (demand_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (capacity_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (required_man_hours >= 0),
  CHECK (effective_man_hours >= 0),
  CHECK (skill_deficit_man_hours >= 0),
  CHECK (demand_pressure_index >= 0),
  CHECK (capacity_gap_man_hours >= 0),
  CHECK (root_cause IN (
    'skill_mix_constraint',
    'manpower_capacity_shortage',
    'execution_or_process',
    'no_pressure_signal'
  )),
  CHECK (automatic_extra_people_permitted = FALSE),
  CHECK (jsonb_typeof(bad_kpi_keys) = 'array'),
  CHECK (jsonb_typeof(kpi_observations) = 'array'),
  CHECK (jsonb_typeof(explanation) = 'array'),
  CHECK (length(trim(created_by)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_dpi_snapshot_interval_idx
  ON workforce_dpi_snapshots(
    tenant_id, location_id, interval_start DESC, created_at DESC
  );

ALTER TABLE workforce_dpi_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_dpi_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_dpi_snapshot_tenant ON workforce_dpi_snapshots;
CREATE POLICY workforce_dpi_snapshot_tenant ON workforce_dpi_snapshots
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

CREATE OR REPLACE FUNCTION workforce_dpi_snapshot_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce DPI snapshots are append-only';
END $$;

DROP TRIGGER IF EXISTS workforce_dpi_snapshot_no_mutation
  ON workforce_dpi_snapshots;
CREATE TRIGGER workforce_dpi_snapshot_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_dpi_snapshots
  FOR EACH ROW EXECUTE FUNCTION workforce_dpi_snapshot_immutable();

INSERT INTO workforce_schema_migrations(version, name)
VALUES (35, 'demand pressure index and root-cause snapshots')
ON CONFLICT (version) DO NOTHING;
