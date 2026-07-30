# PLONAGRAM OS V1.7 — Store DNA + ABC/Catalog Foundation

Bu paket V1.6 DB temelinin üzerine konsey kodlarını kontrollü şekilde oturtur. Direkt App.jsx/main.py overwrite yapılmadı; servisler ve endpointler modülerleştirildi.

## Bu sürüm ne getirir?

- SQLite schema genişletildi:
  - `abc_reports`
  - `abc_items`
  - `catalog_products`
  - `merged_products`
  - `import_jobs`
  - `unplaced_products`
- Backend servis katmanı eklendi:
  - `backend/services/store_dna_service.py`
  - `backend/services/abc_service.py`
  - `backend/services/catalog_service.py`
  - `backend/services/merge_service.py`
- V1.7 endpointleri eklendi:
  - `GET /stores/{store_code}/readiness`
  - `POST /stores/{store_code}/dna/generate-easy`
  - `POST /stores/{store_code}/dna/generate-template`
  - `GET /stores/{store_code}/dna/fixture-pools`
  - `POST /abc/upload?store_code=ANKA`
  - `GET /abc/{store_code}/latest`
  - `POST /catalog/upload?store_code=ANKA`
  - `GET /catalog/status?store_code=ANKA`
  - `GET /catalog/search?store_code=ANKA&q=...`
  - `POST /products/merge`
  - `GET /products/merged/{store_code}`
  - `GET /unplaced/{store_code}/{version_id}`
  - `GET /unplaced/{store_code}/{version_id}/csv`
  - `GET /unplaced/{store_code}/{version_id}/xlsx`
- Frontend Depo Kurulumu ekranı eklendi:
  - Store DNA Wizard
  - Kolay kurulum
  - Şablondan başla
  - Serbest editöre geç
  - ABC + Catalog upload paneli
  - Merge sonucu ürünleri planogram engine’e hazır hale getirme
- Komuta Merkezi’ne hazırlık kartları eklendi:
  - Store DNA durumu
  - ABC/Catalog/Merge durumu
  - Planogram üretime hazır mı?

## Kurulum

Önce yedek al:

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BACKUP_BEFORE_V1_7 /E /I /H
xcopy backend backend_BACKUP_BEFORE_V1_7 /E /I /H
```

ZIP içindeki `frontend` ve `backend` klasörlerini mevcut klasörlerin üzerine kopyala.

Backend:

```bash
cd C:\Users\ErdiAydın\planai\backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Frontend:

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

Kontrol:

```text
http://127.0.0.1:8001/db/health
http://127.0.0.1:8001/stores/ANKA/readiness
```

## Kullanım sırası

1. Depo Kurulumu ekranına gir.
2. Store DNA oluştur ve kaydet.
3. ABC raporu yükle.
4. Catalog data yükle.
5. ABC + Catalog birleştir.
6. Komuta Merkezi’nde hazırlık durumu “Üretime hazır” olunca planogram üret.

## Önemli karar

Bu sürümde SQL/BigQuery zorunlu değil. Kullanıcının yüklediği ABC raporu satış beyni, Catalog data ürün kimliği, Store DNA fiziksel gerçeklik olarak kullanılır.

## Bilinen sonraki işler

- Engine’i fixture-first placement için daha da sertleştirmek.
- Store DNA wizard içinde modül bazlı özel ölçü düzenlemeyi daha ayrıntılı yapmak.
- Atanamayan nedenlerini engine seviyesinde daha standart kodlarla döndürmek.
- Print Center: raf / modül / koridor çıktısını saha PDF kalitesine taşımak.
- 3D editörde resize/rotate/snap/undo-redo güçlendirmek.
