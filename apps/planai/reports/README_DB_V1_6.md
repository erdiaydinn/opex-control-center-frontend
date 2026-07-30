# PLONAGRAM OS DB V1.6

Bu paket V1.5 recovery üzerine SQLite kalıcı veritabanı katmanı ekler.

## Yeni backend dosyaları

- `backend/db.py`
- `backend/db_routes.py`
- `backend/database/plonagram.db` çalışma sırasında otomatik oluşur.

## Yeni endpointler

- `GET /db/health`
- `GET /bootstrap/{store_code}`
- `POST /stores/{store_code}/dna`
- `GET /stores/{store_code}/dna`
- `POST /layouts/{store_code}/save`
- `GET /layouts/{store_code}/latest`
- `GET /layouts/{store_code}/versions`
- `POST /planograms/{store_code}/save`
- `GET /planograms/{store_code}/latest`
- `GET /planograms/{store_code}/versions`
- `POST /tasks`
- `GET /tasks?store_code=ANKA`
- `PATCH /tasks/{task_id}`
- `POST /evidence/upload`
- `GET /evidence/{store_code}`
- `GET /audit/{store_code}`

## Frontend entegrasyonu

- Uygulama açılırken `GET /bootstrap/{store}` çağrılır.
- SKU dosyası yüklendiğinde üretilen planogram otomatik DB’ye kaydedilir.
- Layout dosyası yüklendiğinde layout versiyonu otomatik DB’ye kaydedilir.
- Optimum plan üretildiğinde planogram versiyonu, layout state ve ilk task DB’ye kaydedilir.

## Kurulum

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

## Test

Backend ayaktayken tarayıcıdan kontrol:

```text
http://127.0.0.1:8001/db/health
http://127.0.0.1:8001/bootstrap/ANKA
```

## Not

Bu sürüm PostgreSQL değil, SQLite kullanır. Ama endpoint ve veri modeli PostgreSQL’e taşınabilecek şekilde kuruldu. Canlı yayına geçerken SQLite yerine PostgreSQL adaptörü bağlanmalı.
