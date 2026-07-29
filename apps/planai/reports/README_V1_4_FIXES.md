# PLONAGRAM OS Twin Studio Council v1.4 Fix Pack

Bu paket v1.3 üzerine kritik saha/planogram düzeltmelerini ekler.

## Düzeltilenler

- Command Center altındaki Live Digital Twin alanı statik görsel olmaktan çıkarıldı; gerçek WebGL Twin Studio state'i ile beslendi.
- Üst hero görseli daha temiz premium operasyon görseline çevrildi.
- Operation loading ekranındaki geçici logo kaldırıldı; gerçek PLONAGRAM P monogramı kullanıldı.
- Canlı 3D içindeki gereksiz kamera yardım kartı kaldırıldı; kamera preset dropdown kontrolü çalışır hale getirildi.
- Kamera presetleri, seçili raf/alan state'i yüzünden kilitlenmiyor. Overview / Top / Chilled / Frozen / Dispatch doğrudan çalışır.
- Hayali asma kat ve gereksiz worker/araç karmaşası default kapatıldı. Store DNA'da kat varsa yine desteklenir.
- Product Placement artık modül/shelf bazında gerçek ürün lokasyonuna bakar; tek rafa binlerce ürün yığmaz.
- Product image URL alanları desteklendi: Product Image URL, image_url, catalog_image_url, pim_image_url.
- ABC raporundaki % Orders / % Stops / Rank alanları satış skoru olarak normalize edilir.
- Sebze/meyve ürünleri normal kuru raf yerine PRODUCE_SHELF / meyve sebze rafına yönlendirilir.
- Donuk ürünler -18 / Algida, chilled ürünler +4 / yatay dolap tarafına yönlendirilir.
- Atanamayan ürün raporu Planogram ve Reports ekranına eklendi.
- Planogram 3D sekmesi artık gerçek TwinStudio3D render eder.
- Raf / modül / koridor yazdırma ayrıştırıldı:
  - Raf yazdır: sadece seçili raf
  - Modül yazdır: seçili modülün raf raf görsel ve ürün listesi
  - Koridor yazdır: koridordaki tüm modül ve raflar
- Backend Council layout kapasitesi artırıldı ve PRODUCE_SHELF desteği eklendi.

## Kurulum

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BACKUP_BEFORE_V1_4 /E /I /H
xcopy backend backend_BACKUP_BEFORE_V1_4 /E /I /H
```

ZIP içindeki `frontend` klasörünü mevcut frontend üzerine, `backend` klasörünü mevcut backend üzerine kopyala.

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

Backend:

```bash
cd C:\Users\ErdiAydın\planai\backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Önemli

`backend/data` klasörü yine boş gelir. Eski gerçek data klasörünü geri koy:

```bash
xcopy backend_data_BACKUP backend\data /E /I /H /Y
```
