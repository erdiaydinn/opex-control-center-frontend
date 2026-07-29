# PLONAGRAM OS V1.7.1 Production Candidate

Bu paket V1.7 üzerine konseyin 7 blocker düzeltmesini kontrollü merge eder.

## Ana değişiklikler

- Store DNA save logic V1.7 route yapısında kalıcı DB upsert ile çalışır.
- Merge service spec uyumu:
  - SKU exact = 1.00
  - Barcode exact = 0.98
  - Product key = 0.85
  - Fuzzy match otomatik merge edilmez, review/suggestion olarak döner.
- Store DNA koridor modeli left/right module yapısını destekler.
- Easy Wizard payload artık sol/sağ modül sayısını ve sol/sağ fixture tipini backend'e gönderir.
- Store DNA service produce shelf ve horizontal fridge alanlarını da üretebilir.
- Fixture-first planogram engine eklendi: `backend/services/planogram_engine.py`
- Yeni endpoint eklendi: `POST /planograms/{store_code}/generate-fixture-first`
- Unplaced ürünler planogram versiyonuna ve DB `unplaced_products` tablosuna yazılır.
- Konsey test suite eklendi: `backend/test_production_v17.py`

## Kurulum

Yedek al:

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BACKUP_BEFORE_V1_7_1 /E /I /H
xcopy backend backend_BACKUP_BEFORE_V1_7_1 /E /I /H
```

ZIP içindeki `frontend` ve `backend` klasörlerini mevcut klasörlerin üzerine koy.

Backend:

```bash
cd C:\Users\ErdiAydın\planai\backend
python -m pip install -r requirements.txt
python test_production_v17.py
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Frontend:

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

## Kontrol URL'leri

```text
http://127.0.0.1:8001/db/health
http://127.0.0.1:8001/stores/ANKA/readiness
```

## Önemli not

Bu paket production candidate seviyesidir. Gerçek production onayı için Fulya ABC + gerçek catalog dosyasıyla uçtan uca test yapılmalı:

1. Store DNA oluştur.
2. ABC yükle.
3. Catalog yükle.
4. Merge çalıştır.
5. Match rate ölç.
6. Fixture-first planogram üret.
7. Atanamayan raporunu kontrol et.

