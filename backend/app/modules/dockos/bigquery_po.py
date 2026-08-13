import os


def fetch_live_purchase_orders(supplier_name=None, warehouse_name=None):
    """Optional BigQuery adapter; returns a stable DockOS PO contract."""
    try:
        from google.cloud import bigquery
    except Exception as error:
        return {"source": "ERROR", "message": f"BigQuery paketi yüklenemedi: {error}", "rows": []}

    project = os.getenv("DOCKOS_BQ_PROJECT", "fulfillment-dwh-production")
    try:
        client = bigquery.Client(project=project)
        sql = """
        SELECT
          REGEXP_REPLACE(warehouse.warehouse_name, r'^Yemeksepeti Market\\s*[,;]?\\s*', '') AS warehouse_name,
          CAST(po_order_id AS STRING) AS po_number,
          CAST(supplier_id AS STRING) AS supplier_id,
          supplier_name,
          DATE(pp.created_localtime_at) AS created_date,
          DATE(pp.promised_localtime_at) AS promised_date,
          order_status,
          COUNT(DISTINCT pp.sku_id) AS total_sku
        FROM `fulfillment-dwh-production.curated_data_shared_dmart.purchase_orders`,
          UNNEST(products_purchased) AS pp
        WHERE global_entity_id = 'YS_TR'
          AND LOWER(order_status) NOT IN ('canceled', 'cancelled', 'done')
          AND DATE(pp.created_localtime_at) >= CURRENT_DATE('Europe/Istanbul') - 365
          AND (DATE(pp.promised_localtime_at) IS NULL OR DATE(pp.promised_localtime_at) >= CURRENT_DATE('Europe/Istanbul'))
          AND warehouse.warehouse_name LIKE '%DC%'
          AND warehouse.warehouse_name NOT LIKE '%cDC%'
          AND UPPER(CAST(po_order_id AS STRING)) NOT LIKE '%-UPDATE%'
          AND (@supplier_name IS NULL OR LOWER(supplier_name) = LOWER(@supplier_name))
          AND (@warehouse_name IS NULL OR LOWER(REGEXP_REPLACE(warehouse.warehouse_name, r'^Yemeksepeti Market\\s*[,;]?\\s*', '')) = LOWER(@warehouse_name))
        GROUP BY warehouse_name, po_number, supplier_id, supplier_name, created_date, promised_date, order_status
        ORDER BY promised_date ASC, created_date DESC
        LIMIT 2000
        """
        config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("supplier_name", "STRING", supplier_name),
            bigquery.ScalarQueryParameter("warehouse_name", "STRING", warehouse_name),
        ])
        result = []
        for row in client.query(sql, job_config=config).result(timeout=120):
            result.append({
                "po_number": row.po_number,
                "po_order_id": row.po_number,
                "supplier_id": row.supplier_id,
                "supplier_name": row.supplier_name,
                "warehouse_name": row.warehouse_name,
                "created_date": str(row.created_date) if row.created_date else None,
                "delivery_date": str(row.promised_date) if row.promised_date else None,
                "promised_date": str(row.promised_date) if row.promised_date else None,
                "order_status": row.order_status,
                "status": "OPEN",
                "sku_count": int(row.total_sku or 0),
                "total_sku": int(row.total_sku or 0),
                "pallet_count": 0,
                "source": "BIGQUERY",
            })
        return {"source": "BIGQUERY", "message": "Canlı BigQuery PO verisi kullanılıyor.", "rows": result}
    except Exception as error:
        return {"source": "ERROR", "message": str(error), "rows": []}
