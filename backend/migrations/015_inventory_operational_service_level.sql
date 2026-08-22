-- EAY Inventory v15: server-owned service level metadata for physical missions.
BEGIN;

ALTER TABLE inventory_operational_missions
  ADD COLUMN IF NOT EXISTS priority text NOT NULL DEFAULT 'NORMAL',
  ADD COLUMN IF NOT EXISTS due_at timestamptz,
  ADD COLUMN IF NOT EXISTS estimated_seconds integer;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'inventory_operational_priority_v15'
      AND conrelid = 'inventory_operational_missions'::regclass
  ) THEN
    ALTER TABLE inventory_operational_missions
      ADD CONSTRAINT inventory_operational_priority_v15
      CHECK (priority IN ('LOW','NORMAL','HIGH','URGENT'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'inventory_operational_due_v15'
      AND conrelid = 'inventory_operational_missions'::regclass
  ) THEN
    ALTER TABLE inventory_operational_missions
      ADD CONSTRAINT inventory_operational_due_v15
      CHECK (due_at IS NULL OR due_at >= created_at);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'inventory_operational_estimate_v15'
      AND conrelid = 'inventory_operational_missions'::regclass
  ) THEN
    ALTER TABLE inventory_operational_missions
      ADD CONSTRAINT inventory_operational_estimate_v15
      CHECK (estimated_seconds IS NULL OR estimated_seconds BETWEEN 1 AND 86400);
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS inventory_operational_mobile_queue_v15
  ON inventory_operational_missions(
    tenant_id,
    warehouse_id,
    state,
    priority,
    due_at,
    created_at,
    mission_id
  )
  WHERE state IN ('OPEN','CLAIMED');

INSERT INTO inventory_schema_migrations(version,name)
VALUES(15,'inventory operational service level authority')
ON CONFLICT DO NOTHING;

COMMIT;
