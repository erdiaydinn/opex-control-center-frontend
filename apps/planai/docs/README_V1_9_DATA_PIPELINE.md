# PLONAGRAM OS V1.9 — Data Pipeline Pack

## Amaç

V1.9, planogram doğruluğu için veri kaynaklarını net ayırır:

- **Embedded Catalog**: ürün fiziksel gerçekliği. Ölçü, ağırlık, storage, case pack.
- **ABC Upload**: store-specific talep/görsel/stok sinyali. Görsel, on-hand, % orders, % stops, ABC, rank.
- **Store DNA**: fixture/raf/dolap/soğuk/donuk kapasite gerçekliği.
- **Engine**: hedef lokasyonu belirler.

ABC `Location` ve `Secondary Location` hedef yerleşim kuralı değildir. Sadece Delta Planogram için mevcut lokasyon sinyalidir.

## Eklenen backend dosyaları

```text
backend/services/abc_upload_service.py
backend/services/catalog_abc_merge.py
backend/services/product_visual_resolver.py
backend/routers/data_pipeline_routes.py
backend/tests/test_v19_data_pipeline.py
backend/MAIN_INCLUDE_SNIPPET_v19.py
```

## Eklenen frontend dosyaları

```text
frontend/src/services/plonagramDataPipelineApi.js
frontend/src/components/DataPipeline/ABCUploadPanel.jsx
frontend/src/components/DataPipeline/ABCUploadPanel.css
```

## Backend router ekleme

`backend/main.py` içinde `app = FastAPI(...)` sonrası ekle:

```python
try:
    from routers.data_pipeline_routes import router as data_pipeline_router
    app.include_router(data_pipeline_router)
except Exception as exc:
    print(f"PLONAGRAM V1.9 data-pipeline router disabled: {exc}")
```

## Test

```powershell
cd C:\Users\ErdiAydın\planai\backend
python .\tests\test_v19_data_pipeline.py
```

Beklenen:

```text
✅ V1.9 data pipeline tests passed
```

## Endpointler

```text
POST /data-pipeline/abc/parse
POST /data-pipeline/abc/upload-merge
POST /data-pipeline/abc/merge
POST /data-pipeline/visual/resolve
GET  /data-pipeline/catalog/status
```

## ABC zorunlu kolonları

```text
Country
Store
Rank
Category L1
Category L2
SKU
Product Name
Barcodes
ABC
On-Hand Qty
Storage Type
Product Image URL
% Stops
% Orders
```

Opsiyonel / delta kolonları:

```text
Location
Is A Zone
Secondary Location
```

## Görsel önceliği

```text
1. ABC Product Image URL
2. visual override
3. catalog image_url / catalog_image_url / pim_image_url
4. generated brand/category fallback tile
```

## Storage kararı

```text
1. Catalog storage_type ana gerçekliktir.
2. ABC Storage Type sadece hint olarak tutulur.
3. Çelişki varsa storage_conflict=true ve review listesine düşer.
```
