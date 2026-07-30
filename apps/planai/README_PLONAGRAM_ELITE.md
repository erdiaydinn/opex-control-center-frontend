# Plonagram Elite Final Package

Bu paket, önceki tek dosya App.jsx yamalarını bırakıp Plonagram'ı daha temiz mühendislik mimarisine taşır.

## İçerik

```text
frontend/
  src/
    App.jsx
    App.css
    components/
      Depot3D.jsx
      Planogram2D.jsx
      ShelfEditor.jsx
      RuleEnginePanel.jsx
      AnalyticsPanel.jsx
      FieldPrint.jsx
      EditDialogs.jsx
      TopBar.jsx
    services/api.js
    utils/planogram.js
backend/
  backend/
    main.py
    dxf_parser_smart.py
    requirements.txt
```

## Çalıştırma

### Backend

```bash
cd backend/backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Bu sürümde gelenler

- İlk girişte 3D depo iskeleti görünür; planogram üretmek şart değil.
- 3D ve 2D aynı `planogram` state üzerinden çalışır.
- 3D koridora tıklayınca ayrı çalışma penceresi açılır.
- 2D saha görünümü modül/raf/ürün/facing formatında çalışır.
- Raf editörü popup değil, saha kullanıcısının okuyacağı büyük kartlarla açılır.
- Tek ön yüz yön popup'ları kaldırıldı.
- Dizilim kuralları üretimden önce seçilir: Hibrit, ABC, Kategori, Marka, Toplama, Hacim/Replenishment.
- Raf içinde aynı kurallarla yeniden dizim yapılabilir.
- Modül ekle, raf ekle, modül ölçü, raf ölçü hem 2D hem 3D'de aynı state'e işler.
- Modüler yazdırma ayrı pencere açar: 1 sayfa görsel raf + 1 sayfa ürün listesi.
- JSON export içinde ürünler, layout, planogram, kullanım metrikleri ve action log bulunur.
- Backend'e daha akıllı DXF parser eklendi: layer/block isimlerini ve geometrik filtreyi kullanır.
- Backend'e `/save-usage-log` ve `/usage-logs` endpointleri eklendi.

## Piyasadaki araçlara göre eksik/gelişim rotası

Bu paket frontend/backend akışını toparlayan ciddi başlangıçtır; gerçek pazar liderliği için sonraki sprintler:

1. **Gerçek WebGL/Three.js motoru**: CSS 3D yerine raf/ürün geometry mesh.
2. **DXF layer standardı**: `RACK`, `RAF`, `CHILLED`, `FROZEN`, `DISPATCH`, `INBOUND` layer sözlüğü.
3. **Kalıcı DB loglama**: SQLite/Postgres ile tüm aksiyon, hacim, doluluk, değişiklik geçmişi.
4. **AI Insight endpoint'i**: "Bu depo neden verimsiz?" sorularını metriklerden açıklayan servis.
5. **PDF export servisi**: Frontend print yerine backend PDF render.
6. **Saha compliance**: Mağaza fotoğrafı yükle, raf/ürün farkını AI ile kontrol et.

## Not

`Şükrüpaşa.dxf` gibi gerçek CAD dosyalarında layer isimleri standardize değilse parser tahmin yapar. Parser artık daha seçici, ama kusursuz CAD okuma için layer/block naming standardı şarttır.
