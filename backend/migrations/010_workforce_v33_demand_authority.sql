-- Workforce V33 / roadmap 11/60: versioned labor-standard authority and
-- immutable deterministic demand snapshots. Apply after V32.
--
-- Raw customer operational datasets do not belong here. Records contain only
-- governed standards, provenance references, deterministic demand evidence and
-- tenant-scoped fingerprints.

CREATE TABLE IF NOT EXISTS workforce_labor_standard_versions (
  tenant_id text NOT NULL,
  activity text NOT NULL,
  version integer NOT NULL,
  seconds_per_unit numeric(20,8) NOT NULL,
  people numeric(20,8) NOT NULL DEFAULT 1,
  effective_from timestamptz NOT NULL,
  effective_until timestamptz,
  status text NOT NULL DEFAULT 'approved',
  source_ref text NOT NULL,
  approved_by text NOT NULL,
  authority_fingerprint char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, activity, version),
  UNIQUE (tenant_id, authority_fingerprint),
  CHECK (version > 0),
  CHECK (seconds_per_unit > 0),
  CHECK (people > 0),
  CHECK (status IN ('approved','retired')),
  CHECK (effective_until IS NULL OR effective_until > effective_from),
  CHECK (authority_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (length(trim(source_ref)) > 0),
  CHECK (length(trim(approved_by)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_labor_standard_effective_idx
  ON workforce_labor_standard_versions(
    tenant_id, activity, status, effective_from, effective_until
  );

CREATE TABLE IF NOT EXISTS workforce_demand_snapshots (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  interval_start timestamptz NOT NULL,
  interval_minutes integer NOT NULL,
  model_version text NOT NULL,
  input_fingerprint char(64) NOT NULL,
  snapshot_fingerprint char(64) NOT NULL,
  base_man_hours numeric(24,10) NOT NULL,
  overhead_man_hours numeric(24,10) NOT NULL,
  required_man_hours numeric(24,10) NOT NULL,
  required_people numeric(24,10) NOT NULL,
  labor_standard_refs jsonb NOT NULL,
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
  CHECK (base_man_hours >= 0),
  CHECK (overhead_man_hours >= 0),
  CHECK (required_man_hours >= 0),
  CHECK (required_people >= 0),
  CHECK (jsonb_typeof(labor_standard_refs) = 'array'),
  CHECK (jsonb_typeof(contributors) = 'array'),
  CHECK (length(trim(created_by)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_demand_snapshot_interval_idx
  ON workforce_demand_snapshots(
    tenant_id, location_id, interval_start DESC, model_version
  );

ALTER TABLE workforce_labor_standard_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_labor_standard_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_labor_standard_tenant ON workforce_labor_standard_versions;
CREATE POLICY workforce_labor_standard_tenant ON workforce_labor_standard_versions
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_demand_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_demand_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_demand_snapshot_tenant ON workforce_demand_snapshots;
CREATE POLICY workforce_demand_snapshot_tenant ON workforce_demand_snapshots
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

CREATE OR REPLACE FUNCTION workforce_demand_authority_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce demand authority evidence is append-only';
END $$;

DROP TRIGGER IF EXISTS workforce_labor_standard_no_mutation
  ON workforce_labor_standard_versions;
CREATE TRIGGER workforce_labor_standard_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_labor_standard_versions
  FOR EACH ROW EXECUTE FUNCTION workforce_demand_authority_immutable();

DROP TRIGGER IF EXISTS workforce_demand_snapshot_no_mutation
  ON workforce_demand_snapshots;
CREATE TRIGGER workforce_demand_snapshot_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_demand_snapshots
  FOR EACH ROW EXECUTE FUNCTION workforce_demand_authority_immutable();

INSERT INTO workforce_schema_migrations(version, name)
VALUES (33, 'versioned labor standards and deterministic demand snapshots')
ON CONFLICT (version) DO NOTHING;
