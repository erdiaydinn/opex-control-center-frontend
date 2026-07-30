# PLONAGRAM_CHANGE_FILES_V3

Bu paket sadece değiştirilecek dosyaları içerir.

## Kopyalanacak dosyalar

```txt
frontend/src/App.jsx
frontend/src/App.css
frontend/src/main.jsx
frontend/src/services/api.js
```

## Kurulum

1. Zip'i aç.
2. `src` klasörünü mevcut `C:\Users\ErdiAydın\planai\frontend\src` üzerine kopyala.
3. React 18 uyumlu three paketleri zaten kurulduysa tekrar kurmana gerek yok.
4. Gerekirse:

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm install three@0.160.1 @react-three/fiber@8.17.10 @react-three/drei@9.122.0 --legacy-peer-deps
npm run dev
```

Backend:

```bash
cd C:\Users\ErdiAydın\planai\backend
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Bu pakette gelenler

- PLONAGRAM çizgisel loading ekranı.
- Beyaz/premium tasarım sistemi.
- Çalışan sol menü: Komuta, Canlı 3D, Mimari Düzenleyici, Ürün Yerleşimi, Ürün Kütüphanesi, Fixture, Planogram, Kurallar, Raporlar.
- Gerçek React Three Fiber 3D sahne.
- Orbit / zoom / pan / preset kamera.
- SKU arama ve focus butonu.
- 2D mimari düzenleyicide mouse ile taşıma, seçme, X/Y/W/H/rotation düzenleme.
- Algida, soğuk oda, donuk oda, dispatch, receiving ve kolonlar modül/fixture davranışına geçti.
- CSV yükle, layout yükle, plan üret, layout kaydet, export butonları gerçek aksiyona bağlandı.
- Backend yoksa local fallback ile ekran boş kalmaz.

## Not

Bu tek parça bir görsel kaplama değil; kırılan eski CSS ve eski karanlık mockup görüntüsünü devreden çıkaran yeni App seviyesinde güvenli yeniden bağlama paketidir.
