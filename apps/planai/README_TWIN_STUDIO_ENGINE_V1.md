# PLONAGRAM OS — Twin Studio Engine v1

Bu paket V3 shell'i korur, `Canlı 3D` ekranındaki CSS sahneyi gerçek React Three Fiber / Three.js WebGL motoru ile değiştirir.

## Gelen ana değişiklikler

- `src/components/Live3D/TwinStudio3D.jsx`
- `src/components/Live3D/TwinStudio3D.css`
- `src/components/Live3D/twinDataAdapter.js`
- `src/components/Live3D.jsx` Three.js motoruna bağlandı.
- `package.json` içine Three.js bağımlılıkları eklendi.

## Motor kabiliyetleri

- Gerçek `Canvas`, `PerspectiveCamera`, `OrbitControls`
- Mouse orbit / pan / wheel zoom
- Kamera presetleri: genel bakış, üst görünüm, +4, -18, sevkiyat
- Store layout objelerini gerçek 3D mesh'e dönüştüren adapter
- Raf modülleri, oda hacimleri, kolonlar, dispatch/receiving/facility objeleri
- Ürün marker'ları
- Animated picker route
- Cold-chain route layer
- Forklift/aktif rota aracı
- Refill / congestion / cold-chain alert markerları
- Heatmap modları: satış, refill, soğuk, trafik, tesisler
- Raf tıklayınca büyük raf iç düzenleyici popup açılır
- Alan dropdown + doluluk/modül/raf/yeri değişecek ürün artır-azalt paneli

## Kurulum

Mevcut frontend'i yedekle:

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BACKUP_BEFORE_TWIN_ENGINE /E /I /H
```

ZIP içindeki `frontend` klasörünü mevcut `frontend` üzerine kopyala.

Sonra:

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm install
npm run dev
```

Bu paket için gerekli ek bağımlılıklar:

```bash
npm install three @react-three/fiber @react-three/drei @react-three/postprocessing postprocessing
```

## Önemli karar

Bu paket `App.jsx`'i tek dosyalık 3D demo ile değiştirmez. 3D konseyi tarafından üretilen motor, PLONAGRAM OS içinde ayrı bir motor katmanı olarak bağlandı. Böylece menü, görevler, admin, planogram popup, yayınlama ve mevcut state korunur.

## Sonraki sprint

1. Backend planogram/layout JSON'u `twinDataAdapter` içine bağla.
2. SKU search sonrası gerçek raf seviyesine kamera uçur.
3. Layout Architect 3D editörünü aynı WebGL motoruna geçir.
4. Drag-drop ile gerçek mesh taşıma / rotate / resize ekle.
5. Raf iç ürünlerini ürün görsel URL'leriyle texture'a çevir.
