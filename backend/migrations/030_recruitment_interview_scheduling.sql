-- Hiring V46: candidate self-service interview scheduling authority.
-- Schedules/slots are shared at vacancy+pipeline-stage scope so concurrent
-- candidates compete for the same real capacity. Candidate access remains
-- capability-bound and every mutation rotates the capability.

CREATE TABLE IF NOT EXISTS recruitment.interview_schedules (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  schedule_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  stage text NOT NULL CHECK (btrim(stage) <> ''),
  title text NOT NULL CHECK (btrim(title) <> '' AND length(title) <= 180),
  timezone text NOT NULL CHECK (btrim(timezone) <> '' AND length(timezone) <= 80),
  meeting_mode text NOT NULL CHECK (meeting_mode IN ('ONSITE','REMOTE','PHONE')),
  location_label text NOT NULL DEFAULT '' CHECK (length(location_label) <= 500),
  instructions text NOT NULL DEFAULT '' CHECK (length(instructions) <= 2000),
  duration_minutes integer NOT NULL CHECK (duration_minutes BETWEEN 10 AND 480),
  status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED','CANCELLED')),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  PRIMARY KEY (tenant_id, schedule_id)
);
CREATE INDEX IF NOT EXISTS interview_schedule_request_idx
  ON recruitment.interview_schedules(tenant_id, request_id, stage, status, created_at DESC);

CREATE TABLE IF NOT EXISTS recruitment.interview_slots (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  slot_id uuid NOT NULL,
  schedule_id uuid NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL CHECK (ends_at > starts_at),
  capacity integer NOT NULL DEFAULT 1 CHECK (capacity BETWEEN 1 AND 20),
  status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, slot_id),
  UNIQUE (tenant_id, schedule_id, starts_at),
  FOREIGN KEY (tenant_id, schedule_id)
    REFERENCES recruitment.interview_schedules(tenant_id, schedule_id)
);
CREATE INDEX IF NOT EXISTS interview_slot_schedule_idx
  ON recruitment.interview_slots(tenant_id, schedule_id, starts_at);

CREATE TABLE IF NOT EXISTS recruitment.interview_bookings (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  booking_id uuid NOT NULL,
  schedule_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  slot_id uuid,
  status text NOT NULL CHECK (status IN ('BOOKED','CANCELLED')),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  booked_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, booking_id),
  UNIQUE (tenant_id, schedule_id, candidate_id),
  FOREIGN KEY (tenant_id, schedule_id)
    REFERENCES recruitment.interview_schedules(tenant_id, schedule_id),
  FOREIGN KEY (tenant_id, slot_id)
    REFERENCES recruitment.interview_slots(tenant_id, slot_id)
);
CREATE INDEX IF NOT EXISTS interview_booking_slot_idx
  ON recruitment.interview_bookings(tenant_id, slot_id, status);

CREATE TABLE IF NOT EXISTS recruitment.interview_booking_capabilities (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  capability_id uuid NOT NULL,
  schedule_id uuid NOT NULL,
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  token_sha256 bytea NOT NULL CHECK (octet_length(token_sha256) = 32),
  generation integer NOT NULL CHECK (generation > 0),
  expires_at timestamptz NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  issued_by text NOT NULL CHECK (btrim(issued_by) <> ''),
  revoked_at timestamptz,
  successor_capability_id uuid,
  PRIMARY KEY (tenant_id, capability_id),
  UNIQUE (tenant_id, token_sha256),
  FOREIGN KEY (tenant_id, schedule_id)
    REFERENCES recruitment.interview_schedules(tenant_id, schedule_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS interview_candidate_active_capability_idx
  ON recruitment.interview_booking_capabilities(tenant_id, schedule_id, candidate_id)
  WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS interview_capability_expiry_idx
  ON recruitment.interview_booking_capabilities(tenant_id, expires_at)
  WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS recruitment.interview_booking_events (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  event_id uuid NOT NULL,
  booking_id uuid NOT NULL,
  schedule_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  from_slot_id uuid,
  to_slot_id uuid,
  event_type text NOT NULL CHECK (event_type IN ('BOOKED','RESCHEDULED','CANCELLED')),
  actor_type text NOT NULL CHECK (actor_type IN ('CANDIDATE_CAPABILITY','HR','SYSTEM')),
  actor_ref text NOT NULL CHECK (btrim(actor_ref) <> ''),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  PRIMARY KEY (tenant_id, event_id)
);
CREATE INDEX IF NOT EXISTS interview_booking_event_subject_idx
  ON recruitment.interview_booking_events(tenant_id, schedule_id, candidate_id, occurred_at DESC);

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'interview_schedules','interview_slots','interview_bookings',
    'interview_booking_capabilities','interview_booking_events'
  ] LOOP
    EXECUTE format('ALTER TABLE recruitment.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE recruitment.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON recruitment.%I', table_name || '_tenant_policy', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON recruitment.%I USING (tenant_id = public.workforce_current_tenant()) WITH CHECK (tenant_id = public.workforce_current_tenant())',
      table_name || '_tenant_policy', table_name
    );
    EXECUTE format('REVOKE ALL ON TABLE recruitment.%I FROM PUBLIC', table_name);
  END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.reject_interview_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='interview booking event is append-only';
END;
$$;
DROP TRIGGER IF EXISTS interview_booking_event_no_mutation ON recruitment.interview_booking_events;
CREATE TRIGGER interview_booking_event_no_mutation
BEFORE UPDATE OR DELETE ON recruitment.interview_booking_events
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_interview_event_mutation();

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='workforce_runtime') THEN
    GRANT USAGE ON SCHEMA recruitment TO workforce_runtime;
    GRANT SELECT,INSERT,UPDATE ON recruitment.interview_schedules,
      recruitment.interview_slots,recruitment.interview_bookings,
      recruitment.interview_booking_capabilities TO workforce_runtime;
    GRANT SELECT,INSERT ON recruitment.interview_booking_events TO workforce_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (46, 'shared candidate self-service interview scheduling authority')
ON CONFLICT (version) DO NOTHING;
