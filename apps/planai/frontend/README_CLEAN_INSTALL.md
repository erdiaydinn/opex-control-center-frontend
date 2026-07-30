# PLONAGRAM OS Clean Redesign

Bu paket eski CSS ve eski App karmaşasını devreden çıkarır. Tek giriş noktası `src/App.jsx`, tek ana stil dosyası `src/App.css`.

## Kurulum

1. Mevcut frontend klasöründe yedek al:

```bash
cd C:\Users\ErdiAydın\planai\frontend
copy src\App.jsx src\App.backup.jsx
copy src\App.css src\App.backup.css
```

2. Bu paketteki dosyaları mevcut frontend içine kopyala:

```text
src/App.jsx
src/App.css
src/main.jsx
```

3. Eski tasarım sızıntılarını kesmek için `App.jsx` içinde artık şu dosyalar import edilmemeli:

```text
App.extra.css
App.premium.css
App.ultra.css
hotfix css dosyaları
components/App.jsx
```

4. Çalıştır:

```bash
npm run dev
```

Backend varsa otomatik `http://127.0.0.1:8001/master-products?limit=200` endpointini dener. Backend yoksa mock data ile açılır.

## Not

Bu sürüm tek part temiz frontend redesign paketidir. Eski componentleri import etmediği için siyah arka plan, ham HTML fallback ve font karmaşası engellenir.
