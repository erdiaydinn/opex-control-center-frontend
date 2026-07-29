# PLONAGRAM CORE v1

Bu paket patch değil; App + 3D + Rule Engine + Shelf Editor + Auth + Darkstore AI optimizer aynı mimaride birleştirilmiş sürümdür.

## Kurulum

1) ZIP'i aç.
2) `frontend` klasörünü mevcut `C:\Users\ErdiAydin\planai\frontend` üzerine kopyala.
3) Backend değişmeyecekse sadece frontend çalıştır:

```bash
cd C:\Users\ErdiAydin\planai\frontend
npm install
npm install three @react-three/fiber @react-three/drei
npm run dev
```

Backend:

```bash
cd C:\Users\ErdiAydin\planai\backend
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## İçerik

- Auth ekranı: `src/components/auth/`
- Gerçek 3D scene: `src/components/Depot3D.jsx`
- Rack-island layout editor: A/B, C/D gibi karşılıklı raf adalarını birlikte taşır
- İleri seviye kural setleri: `RuleEnginePanel.jsx`
- Raf editörü: ön yüz artır/azalt, ürünü taşı, boş alana ürün ekle, rafı sırala
- Darkstore optimizer: `src/utils/planogram.js`
- 2D saha görünümü korunur
- Analytics ve JSON export korunur

## Kritik not

Bu sürümde `APP_PATCH_ADVANCED_RULES` manuel uygulanmaz. Zaten App içine bağlanmıştır.
