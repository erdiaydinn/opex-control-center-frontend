# PLONAGRAM OS — Twin Studio Council Patch v1.2

Bu paket, konseyin gönderdiği yeni React Three Fiber kodundaki doğru fikirleri mevcut PLONAGRAM OS yapısına entegre eder.

## Ne eklendi?

- Kat sistemi: Zemin Kat / Asma Kat seçici
- Tüm katları birlikte gösterme modu
- Asma kat metal platformu ve korkulukları
- Merdiven / kat geçiş mesh'i
- Picker / worker canlı animasyon katmanı
- Daha ince, raf mantığına daha yakın slim rack mesh yapısı
- Kat bazlı route, alert ve picker görünürlüğü
- Kat değiştiğinde kamera kısa fly-to yapar, sonra kullanıcı kontrolü bırakılmaz
- Eski kamera patch korunur: mouse orbit/pan/wheel zoom ve W/A/S/D devam eder

## Bilerek yapılmayan şey

Konsey kodu doğrudan App.jsx olarak basılmadı. Çünkü o kod kendi mock `warehouseData` modelini kullanıyor ve PLONAGRAM OS state, i18n, raf popup, görev, admin ve yayınlama akışını koparırdı.

Bu paket yalnızca `Live3D/TwinStudio3D.jsx`, `Live3D/TwinStudio3D.css` ve `Live3D/twinDataAdapter.js` katmanını günceller.

## Kurulum

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BACKUP_BEFORE_COUNCIL_V1_2 /E /I /H
```

ZIP içindeki `frontend` klasörünü mevcut `frontend` üzerine kopyala.

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

## Not

`package-lock.json` özellikle pakete konmadı. Böylece internal OpenAI registry URL'si tekrar taşınmaz.
