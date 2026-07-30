# Plonagram V1.9.46 Strategy-first SAFE Pack

Bu paket, konseyin verdiği 1-5 düzeltmelerini iki güvenlik düzeltmesiyle uygular:

1. App.jsx hâlâ `./utils/planogramAllocatorV2.js` import ettiği için allocator dosyası hem `planogramAllocator.js` hem `planogramAllocatorV2.js` olarak verildi.
2. SKU yükleme sırasında `api.savePlanogram(... source: sku_upload_candidates ...)` çağrısı kaldırıldı. SKU yükleme mevcut planı boş planla ezmesin diye ürünler sadece frontend aday havuzuna alınır.

Kopyalama hedefleri:
- App.jsx -> frontend/src/App.jsx
- RuleEngineReal.jsx -> frontend/src/components/RuleEngineReal.jsx
- placementRuleAdapter.js -> frontend/src/utils/placementRuleAdapter.js
- planogramAllocatorV2.js -> frontend/src/utils/planogramAllocatorV2.js
- planogramAllocator.js -> frontend/src/utils/planogramAllocator.js (opsiyonel ama tutarlılık için önerilir)

Uygulama sonrası:
cd frontend
npm run build
npm run dev -- --host 0.0.0.0 --port 5174

Console temizliği:
localStorage.removeItem("plonagram_strategy_profile");
localStorage.removeItem("plonagram_strategy_confirmed");
localStorage.removeItem("plonagram_placement_rules");
localStorage.removeItem("plonagram_optimization_weights");
location.reload();
