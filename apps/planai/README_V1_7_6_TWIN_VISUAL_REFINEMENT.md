# PLONAGRAM OS V1.7.6 — Twin Studio Visual Refinement Patch

Bu patch V1.7.5 üzerine ince işçilik düzeltmesidir. Engine/physics trace katmanını değiştirmez.

## Değişen ana alanlar

- `frontend/src/components/LayoutArchitect.jsx`
  - 3D Editor crash fix: `setDragMode is not a function` hatası düzeltildi.
  - 3D Editor artık `dragMode`, `setDragMode`, `onMoveObject` prop'larını doğru geçirir.

- `frontend/src/components/Live3D/TwinStudio3D.jsx`
  - Raflar sadece transparan blok gibi durmasın diye raf başına fiziksel ürün/kutu görseli eklendi.
  - Raf dikmeleri daha gerçekçi metal görünüme çekildi.
  - Raf yüzeyi daha okunabilir, seçili/hover state daha kontrollü hale getirildi.

- `frontend/src/components/Live3D/TwinStudio3D.css`
  - 3D canvas sahnesi daha premium derinlik, kontur ve okunabilir overlay ile güncellendi.
  - Fullscreen ve editor sahnesinde kontrol çakışmaları azaltıldı.

- `frontend/src/styles/components.css`
  - Layout Architect 3D editör alanı genişletildi.
  - Responsive kırılımlarda sıkışma azaltıldı.

## Bilerek dokunulmadı

- Backend engine kararları
- Store DNA / ABC / embedded catalog akışı
- Physical capacity / trace gate
- Database klasörü

## Kurulum

```powershell
robocopy C:\Users\ErdiAydın\Downloads\v176\frontend C:\Users\ErdiAydın\planai\frontend /E /XD node_modules dist
```

Backend değişikliği zorunlu değil.

## Test

```powershell
cd C:\Users\ErdiAydın\planai\frontend
npm run dev -- --host 0.0.0.0 --port 5174
```

Kontrol listesi:

1. Canlı 3D açılır.
2. Mimari Düzenleyici > 3D Editor açılır.
3. Konsolda `setDragMode is not a function` hatası yoktur.
4. Mouse ile taşı butonu açıldığında obje sürüklenir.
5. Raflar daha dolu/gerçekçi görünür.
