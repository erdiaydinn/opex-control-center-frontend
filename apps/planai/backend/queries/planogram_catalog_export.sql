-- =====================================================
-- PLONAGRAM CATALOG EXPORT
-- Amaç:
-- - Tekil SKU catalog datası
-- - Ölçü, kategori, marka, tedarikçi, storage bilgisi
-- - 1 cm / null / bozuk ölçüleri işaretleme
-- - Planogram cleaner için temiz input
-- =====================================================

WITH catalog_raw AS (
  SELECT
    global_entity_id,

    CAST(sku AS STRING) AS sku,
    CAST(pim_product_id AS STRING) AS pim_product_id,
    CAST(catalog_global_product_id AS STRING) AS catalog_global_product_id,

    -- Barkod alanı bu tabloda çoğunlukla STRING gibi davranıyor.
    -- ARRAY_TO_STRING kullanmıyoruz; daha önce hata vermişti.
    CAST(product_barcodes AS STRING) AS product_barcodes,

    COALESCE(
      product_name_local,
      pim_product_name_local,
      product_name_english,
      pim_product_name_english
    ) AS product_name,

    product_name_local,
    product_name_english,
    pim_product_name_local,
    pim_product_name_english,

    brand_name,

    COALESCE(
      brand_owner_name_local,
      brand_owner_name_english
    ) AS supplier_name,

    brand_owner_name_local,
    brand_owner_name_english,

    frontend_category_local,
    frontend_subcategory_local,
    frontend_category,
    frontend_subcategory,

    pim_category_names.level_one   AS pim_cat_l1,
    pim_category_names.level_two   AS pim_cat_l2,
    pim_category_names.level_three AS pim_cat_l3,
    pim_category_names.level_four  AS pim_cat_l4,

    storage_type AS storage_type_raw,

    SAFE_CAST(product_width_in_cm  AS FLOAT64) AS product_width_in_cm,
    SAFE_CAST(product_height_in_cm AS FLOAT64) AS product_height_in_cm,
    SAFE_CAST(product_length_in_cm AS FLOAT64) AS product_length_in_cm,

    SAFE_CAST(product_weight_value AS FLOAT64) AS product_weight_value,
    product_weight_unit,

    -- Ölçü kalite flagleri
    CASE
      WHEN SAFE_CAST(product_width_in_cm AS FLOAT64) IS NULL
        OR SAFE_CAST(product_height_in_cm AS FLOAT64) IS NULL
        OR SAFE_CAST(product_length_in_cm AS FLOAT64) IS NULL
      THEN 'MISSING_DIMENSION'

      WHEN SAFE_CAST(product_width_in_cm AS FLOAT64) <= 2
        OR SAFE_CAST(product_height_in_cm AS FLOAT64) <= 2
        OR SAFE_CAST(product_length_in_cm AS FLOAT64) <= 2
      THEN 'DIRTY_TOO_SMALL'

      WHEN SAFE_CAST(product_width_in_cm AS FLOAT64) > 120
        OR SAFE_CAST(product_height_in_cm AS FLOAT64) > 160
        OR SAFE_CAST(product_length_in_cm AS FLOAT64) > 120
      THEN 'DIRTY_TOO_LARGE_OR_CASE'

      ELSE 'VALID_DIMENSION'
    END AS dimension_issue_raw,

    ROUND(
      COALESCE(SAFE_CAST(product_width_in_cm AS FLOAT64), 0)
      * COALESCE(SAFE_CAST(product_height_in_cm AS FLOAT64), 0)
      * COALESCE(SAFE_CAST(product_length_in_cm AS FLOAT64), 0),
      2
    ) AS product_volume_cm3,

    CASE
      WHEN SAFE_CAST(product_width_in_cm AS FLOAT64) > 2
       AND SAFE_CAST(product_height_in_cm AS FLOAT64) > 2
       AND SAFE_CAST(product_length_in_cm AS FLOAT64) > 2
       AND SAFE_CAST(product_width_in_cm AS FLOAT64) <= 120
       AND SAFE_CAST(product_height_in_cm AS FLOAT64) <= 160
       AND SAFE_CAST(product_length_in_cm AS FLOAT64) <= 120
      THEN 1
      ELSE 0
    END AS valid_dimension_flag,

    -- Storage ön-temizlik. Final kararı local cleaner da tekrar kontrol edecek.
    CASE
      WHEN REGEXP_CONTAINS(
        LOWER(CONCAT(
          IFNULL(storage_type, ''), ' ',
          IFNULL(product_name_local, ''), ' ',
          IFNULL(product_name_english, ''), ' ',
          IFNULL(frontend_category_local, ''), ' ',
          IFNULL(frontend_subcategory_local, ''), ' ',
          IFNULL(pim_category_names.level_one, ''), ' ',
          IFNULL(pim_category_names.level_two, ''), ' ',
          IFNULL(brand_name, '')
        )),
        r'(frozen|donuk|dondurma|dondurulmuş|dondurulmus|-18|freezer|algida|la lorraine)'
      )
      THEN 'FROZEN'

      WHEN REGEXP_CONTAINS(
        LOWER(CONCAT(
          IFNULL(storage_type, ''), ' ',
          IFNULL(product_name_local, ''), ' ',
          IFNULL(product_name_english, ''), ' ',
          IFNULL(frontend_category_local, ''), ' ',
          IFNULL(frontend_subcategory_local, ''), ' ',
          IFNULL(pim_category_names.level_one, ''), ' ',
          IFNULL(pim_category_names.level_two, ''), ' ',
          IFNULL(brand_name, '')
        )),
        r'(chilled|soğuk|soguk|\+4|fridge|süt|sut|yoğurt|yogurt|peynir|ayran|kefir|sushi|somon|salmon|şarküteri|sarkuteri|et|tavuk)'
      )
      THEN 'CHILLED'

      ELSE 'AMBIENT'
    END AS storage_type_preclean

  FROM `fulfillment-dwh-production.pandata_datamart.pandora__vendor_products_qcomm_catalog_details`
  WHERE global_entity_id = 'YS_TR'
    AND sku IS NOT NULL
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY sku
      ORDER BY
        valid_dimension_flag DESC,
        product_volume_cm3 DESC,
        CASE WHEN product_name IS NOT NULL THEN 1 ELSE 0 END DESC,
        CASE WHEN product_barcodes IS NOT NULL THEN 1 ELSE 0 END DESC,
        CASE WHEN brand_name IS NOT NULL THEN 1 ELSE 0 END DESC
    ) AS rn
  FROM catalog_raw
)

SELECT
  global_entity_id,

  sku,
  pim_product_id,
  catalog_global_product_id,
  product_barcodes,

  product_name,
  product_name_local,
  product_name_english,
  pim_product_name_local,
  pim_product_name_english,

  brand_name,
  supplier_name,
  brand_owner_name_local,
  brand_owner_name_english,

  frontend_category_local,
  frontend_subcategory_local,
  frontend_category,
  frontend_subcategory,

  pim_cat_l1,
  pim_cat_l2,
  pim_cat_l3,
  pim_cat_l4,

  storage_type_raw,
  storage_type_preclean,

  product_width_in_cm,
  product_height_in_cm,
  product_length_in_cm,
  product_weight_value,
  product_weight_unit,

  valid_dimension_flag,
  dimension_issue_raw,
  product_volume_cm3,

  -- Cleaner’ın kolay okuması için alias kolonlar
  product_barcodes AS barcode,
  brand_name AS brand,
  supplier_name AS supplier,
  frontend_category_local AS category_l1,
  frontend_subcategory_local AS category_l2,
  pim_cat_l3 AS category_l3,
  storage_type_raw AS storage_type,

  product_width_in_cm AS width_cm,
  product_height_in_cm AS height_cm,
  product_length_in_cm AS depth_cm,
  product_weight_value AS weight_kg

FROM ranked
WHERE rn = 1
ORDER BY
  storage_type_preclean,
  category_l1,
  category_l2,
  brand,
  product_name;