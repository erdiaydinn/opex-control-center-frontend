# PLONAGRAM OS V1.9.4 — Frontend Wiring & Twin Smoke Patch

Amaç:
- V1.9.3 backend visual twin payload'unu frontend'e bağlamak.
- ABC upload sonrası sellable/excluded/review/image coverage kartlarını göstermek.
- 3D Twin'de ürün adlarını floating label yapmak yerine image tile bileşeni vermek.

Eklenen dosyalar:
- frontend/src/services/plonagramV194Api.js
- frontend/src/components/DataPipeline/ABCUploadPanelV194.jsx
- frontend/src/components/DataPipeline/ABCUploadPanelV194.css
- frontend/src/components/Live3D/ProductTile3DV194.jsx
- frontend/src/components/Live3D/ShelfProductTilesV194.jsx
- frontend/src/components/Live3D/ShelfProductTilesV194.css
- frontend/src/components/CommandCenter/V194PipelineStatusCard.jsx

Kurulum:
```powershell
robocopy "C:\Users\ErdiAydın\Downloads\PLONAGRAM_OS_V1_9_4_FRONTEND_WIRING_TWIN_SMOKE_PATCH\frontend" "C:\Users\ErdiAydın\planai\frontend" /E /XD node_modules dist .git
```

Frontend paketleri:
```powershell
cd C:\Users\ErdiAydın\planai\frontend
npm install
npm install three @react-three/fiber @react-three/drei lucide-react
npm run build
npm run dev -- --host 0.0.0.0 --port 5174
```

Kullanım:
- ABCUploadPanelV194 bileşenini Command Center veya Product Placement ekranına import et.
- onTwinPayloadReady callback'i ile Twin scene state'ine payload ver.
- ShelfProductTilesV194 bileşenini raf ürünleri render edilen yerde kullan.

Örnek:
```jsx
import ABCUploadPanelV194 from "./components/DataPipeline/ABCUploadPanelV194";
import ShelfProductTilesV194 from "./components/Live3D/ShelfProductTilesV194";

<ABCUploadPanelV194 storeCode={activeStore} onTwinPayloadReady={setTwinPayload} />
<ShelfProductTilesV194 products={shelf.products} onSelectProduct={setSelectedProduct} />
```

Smoke acceptance:
- npm run build geçmeli.
- localhost:5174 açılmalı.
- ABC upload paneli görünmeli.
- Upload sonrası sellable/excluded/review/image coverage kartları dolmalı.
- Ürünler image tile olarak görünmeli; isim sadece hover/title olarak görünmeli.
