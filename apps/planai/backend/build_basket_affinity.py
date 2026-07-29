from google.cloud import bigquery
from google_auth_oauthlib.flow import InstalledAppFlow
import pandas as pd
import os

os.makedirs("data", exist_ok=True)

print("Google OAuth login başlatılıyor...")

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    SCOPES
)

credentials = flow.run_local_server(port=0)

client = bigquery.Client(
    credentials=credentials,
    project="focal-furnace-389111"
)

QUERY = r"""
WITH basket AS (
  SELECT
    q.order_id,
    REGEXP_EXTRACT(q.order_id, r'^([A-Za-z0-9]+)-') AS vendor_id,
    q.order_created_date_lt AS order_date,
    CAST(i.sku AS STRING) AS sku
  FROM `fulfillment-dwh-production.curated_data_shared_dmart.qc_orders` q,
  UNNEST(q.items) AS i
  WHERE q.global_entity_id = 'YS_TR'
    AND q.order_created_date_utc BETWEEN DATE_SUB(CURRENT_DATE("Europe/Istanbul"), INTERVAL 365 DAY)
                                     AND DATE_SUB(CURRENT_DATE("Europe/Istanbul"), INTERVAL 1 DAY)
    AND q.is_successful = TRUE
    AND COALESCE(q.is_preorder, FALSE) = FALSE
    AND q.is_dmart = TRUE
    AND i.sku IS NOT NULL
    AND COALESCE(i.quantity_sold, i.quantity_delivered, i.quantity_ordered, 0) > 0
),

pairs AS (
  SELECT
    a.vendor_id,
    a.sku AS sku_a,
    b.sku AS sku_b,
    COUNT(*) AS together_count,
    SUM(
      CASE
        WHEN a.order_date >= DATE_SUB(CURRENT_DATE("Europe/Istanbul"), INTERVAL 30 DAY) THEN 1.5
        WHEN a.order_date >= DATE_SUB(CURRENT_DATE("Europe/Istanbul"), INTERVAL 90 DAY) THEN 1.0
        ELSE 0.35
      END
    ) AS weighted_affinity_score
  FROM basket a
  JOIN basket b
    ON a.order_id = b.order_id
   AND a.vendor_id = b.vendor_id
   AND a.sku < b.sku
  GROUP BY 1,2,3
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY vendor_id, sku_a
      ORDER BY weighted_affinity_score DESC, together_count DESC
    ) AS rn
  FROM pairs
  WHERE together_count >= 20
)

SELECT
  vendor_id,
  sku_a,
  sku_b,
  together_count,
  ROUND(weighted_affinity_score, 2) AS weighted_affinity_score
FROM ranked
WHERE rn <= 20
ORDER BY weighted_affinity_score DESC
"""

print("BigQuery sorgusu çalışıyor...")

df = client.query(QUERY).to_dataframe()

print("Toplam satır:", len(df))

parquet_path = "data/basket_affinity_top.parquet"
csv_path = "data/basket_affinity_top.csv"

df.to_parquet(parquet_path, index=False)

df.to_csv(
    csv_path,
    index=False,
    encoding="utf-8-sig"
)

print("Tamamlandı.")
print("Parquet:", parquet_path)
print("CSV:", csv_path)