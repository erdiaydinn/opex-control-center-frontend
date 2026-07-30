# V1.9.47 Strategy Pipeline Fix

Bu paket V1.9.46 üzerindeki asıl hatayı düzeltir:

1. SKU yükleyince plan otomatik uygulanmaz.
2. App import yolu artık `planogramAllocator.js` üzerinden çalışır.
3. `planogramAllocatorV2.js` de aynı içerikle verilir; eski import kalsa bile aynı motor çalışır.
4. `buildStorePlan` adapter tarafından stratejiye göre sıralanmış ürün sırasını bozmaz.
5. Kategori stratejisinde `brand_block_rank` artık gizlice hibrit sıralama gibi çalışmaz.
6. Manuel kuraldaki `preferred_aisle` gerçek hedef alan olarak slot seçimine girer.

Doğrulama:
- Browser console: `window.__PLONAGRAM_ACTIVE_PIPELINE__` => `V1.9.47_STRATEGY_FIRST_ACTIVE`
- PowerShell: App.jsx içinde `Düzeltme #1` ve `source: 'sku_upload'` olmamalı.
