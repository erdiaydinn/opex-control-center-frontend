# PLONAGRAM OS — Twin Studio Camera Control v1.1

Bu paket Twin Studio Engine v1 üzerine kamera kontrol düzeltmesi getirir.

## Ne değişti?

- Kamera artık her frame otomatik preset noktasına geri çekilmez.
- Kullanıcı mouse ile sahneye dokunduğunda manuel kamera modu devreye girer.
- Preset / SKU / alan değişince kısa fly-to animasyonu çalışır, sonra kontrol kullanıcıda kalır.
- Sol mouse sürükle: orbit/döndür.
- Sağ mouse sürükle: pan/kaydır.
- Mouse wheel: daha hızlı zoom.
- W/A/S/D veya yön tuşları: sahada kamera kaydırma.
- Sağ tık context menu Canvas üzerinde engellendi.
- Kamera kullanım yardım kartı eklendi.

## Kurulum

ZIP içindeki `frontend` klasörünü mevcut frontend üzerine kopyala.

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

Eğer sadece dosya patch istiyorsan değişen ana dosyalar:

- `frontend/src/components/Live3D/TwinStudio3D.jsx`
- `frontend/src/components/Live3D/TwinStudio3D.css`
- `frontend/src/components/Live3D.jsx`

Not: package-lock.json özellikle paketten çıkarıldı; internal OpenAI registry timeout hatasını tekrar üretmemesi için temiz kurulum public npm üzerinden yapılmalı.
