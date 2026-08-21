-- Workforce V31: preserve the approved temporary +1 norm window and make its
-- automatic reversion explicit. Recruitment and Workforce continue to share
-- the existing Employee Master snapshot; this migration creates no competing
-- employee database.

WITH temporary_warehouses(warehouse) AS (
  VALUES
    ('Dicle (Diyarbakır)'), ('Yenikent (İstanbul)'), ('Muratpaşa (Antalya)'),
    ('Lara (Antalya)'), ('Yıldırım (Bursa)'), ('Çorlu (Tekirdağ)'),
    ('Mimaroba (İstanbul)'), ('Konyaaltı (Antalya)'), ('Tuzla (İstanbul)'),
    ('Kartal Cumhuriyet (İstanbul)'), ('Fatih (İstanbul)'), ('Anka (İstanbul)'),
    ('Çekmeköy (İstanbul)'), ('Bayrampaşa (İstanbul)'), ('İsmetpaşa (Çanakkale)'),
    ('Bahçeşehir 2. Kısım (İstanbul)'), ('Çiğli (İzmir)'), ('Tuğba (İstanbul)'),
    ('Anadolu Hisarı (İstanbul)')
)
UPDATE recruitment_norms AS norms
SET payload = jsonb_set(
                jsonb_set(
                  jsonb_set(
                    jsonb_set(
                      jsonb_set(norms.payload, '{base_norm}', to_jsonb((norms.payload->>'norm')::integer), true),
                      '{norm}', to_jsonb((norms.payload->>'norm')::integer + 1), true),
                    '{temporary_adjustment}', '1'::jsonb, true),
                  '{temporary_effective_from}', '"2026-07-01"'::jsonb, true),
                '{temporary_effective_until}', '"2026-09-30"'::jsonb, true
              ) || jsonb_build_object('reversion_mode', 'AUTOMATIC_REVIEW'),
    updated_at = now()
FROM temporary_warehouses
WHERE norms.warehouse = temporary_warehouses.warehouse
  AND NOT (norms.payload ? 'base_norm');

INSERT INTO workforce_schema_migrations(version, name)
VALUES (31, 'workforce hiring lifecycle and temporary norm acceptance')
ON CONFLICT (version) DO NOTHING;
