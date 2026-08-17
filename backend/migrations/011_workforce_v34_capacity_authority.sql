-- Workforce V34 / roadmap 12/60: effective-capacity authority.
--
-- Capacity snapshots are derived, immutable operational evidence. They preserve
-- scheduled, absence, break, unavailable and skill-feasibility components so
-- downstream DPI/replanning never treats roster headcount as usable capacity.

CREATE TABLE IF NOT EXISTS workforce_capacity_snapshots (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  interval_start timestamptz NOT NULL,
  interval_minutes integer NOT NULL,
  model_version text NOT NULL,
  input_fingerprint char(64) NOT NULL,
  snapshot_fingerprint char(64) NOT NULL,
  scheduled_man_hours numeric(24,10) NOT NULL,
  absence_man_hours numeric(24,10) NOT NULL,
  break_man_hours numeric(24,10) NOT NULL,
  unavailable_man_hours numeric(24,10) NOT NULL,
  net_available_man_hours numeric(24,10) NOT NULL,
  skill_feasible_man_hours numeric(24,10) NOT NULL,
  skill_deficit_man_hours numeric(24,10) NOT NULL,
  productivity_factor numeric(20,10) NOT NULL,
  effective_man_hours numeric(24,10) NOT NULL,
  scheduled_fte numeric(24,10) NOT NULL,
  effective_capacity numeric(24,10) NOT NULL,
  skill_deficits jsonb NOT NULL,
  unused_worker_hours jsonb NOT NULL,
  source_refs jsonb NOT NULL,
  contributors jsonb NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, snapshot_fingerprint),
  CHECK (interval_minutes IN (15,30,60)),
  CHECK (length(trim(location_id)) > 0),
  CHECK (length(trim(model_version)) > 0),
  CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (scheduled_man_hours >= 0),
  CHECK (absence_man_hours >= 0),
  CHECK (break_man_hours >= 0),
  CHECK (unavailable_man_hours >= 0),
  CHECK (net_available_man_hours >= 0),
  CHECK (skill_feasible_man_hours >= 0),
  CHECK (skill_deficit_man_hours >= 0),
  CHECK (productivity_factor > 0 AND productivity_factor <= 1.5),
  CHECK (effective_man_hours >= 0),
  CHECK (scheduled_fte >= 0),
  CHECK (effective_capacity >= 0),
  CHECK (jsonb_typeof(skill_deficits) = 'object'),
  CHECK (jsonb_typeof(unused_worker_hours) = 'object'),
  CHECK (jsonb_typeof(source_refs) = 'array'),
  CHECK (jsonb_array_length(source_refs) > 0),
  CHECK (jsonb_typeof(contributors) = 'array'),
  CHECK (length(trim(created_by)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_capacity_snapshot_interval_idx
  ON workforce_capacity_snapshots(
    tenant_id, location_id, interval_start DESC, created_at DESC
  );

ALTER TABLE workforce_capacity_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_capacity_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_capacity_snapshot_tenant ON workforce_capacity_snapshots;
CREATE POLICY workforce_capacity_snapshot_tenant ON workforce_capacity_snapshots
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

CREATE OR REPLACE FUNCTION workforce_capacity_snapshot_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce capacity snapshots are append-only';
END $$;

DROP TRIGGER IF EXISTS workforce_capacity_snapshot_no_mutation
  ON workforce_capacity_snapshots;
CREATE TRIGGER workforce_capacity_snapshot_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_capacity_snapshots
  FOR EACH ROW EXECUTE FUNCTION workforce_capacity_snapshot_immutable();

INSERT INTO workforce_schema_migrations(version, name)
VALUES (34, 'effective capacity snapshots')
ON CONFLICT (version) DO NOTHING;
