BEGIN;

ALTER TABLE dockos.suppliers FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.distribution_centers FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.supplier_access FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.purchase_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.slot_capacity FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.supplier_slot_capacity FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.supplier_daily_limits FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.reservations FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.reservation_purchase_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.notification_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE dockos.settings FORCE ROW LEVEL SECURITY;

CREATE UNIQUE INDEX IF NOT EXISTS audit_request_id_uk
  ON dockos.audit_events (tenant_id, request_id)
  WHERE request_id IS NOT NULL;

CREATE OR REPLACE FUNCTION dockos.audit_append_only_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'DockOS audit_events is append-only';
END;
$$;
DROP TRIGGER IF EXISTS audit_events_append_only ON dockos.audit_events;
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON dockos.audit_events
FOR EACH ROW EXECUTE FUNCTION dockos.audit_append_only_guard();

INSERT INTO dockos.schema_migrations(version) VALUES ('002_runtime_hardening') ON CONFLICT DO NOTHING;
COMMIT;
