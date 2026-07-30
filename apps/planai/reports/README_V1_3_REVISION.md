# PLONAGRAM OS Twin Studio Council v1.3

Bu revizyon, son ekrandaki sorunlar ve Council Engine kararları için hazırlanmıştır.

## Ne düzeltildi

### Frontend
- SKU CSV yükleme artık tarayıcı içinde de çalışır; backend açıksa `/upload-products-csv` üzerinden enrichment alır.
- XLSX yükleme backend üzerinden desteklenir.
- Layout yükleme DXF ve JSON destekler.
- Tüm dosya yükleme ve optimum plan üretme sırasında PLONAGRAM loading overlay açılır.
- Loading overlay içinde işlem adımları, planogram bilgilendirme cümleleri ve iptal butonu bulunur.
- İptal edilirse mevcut state korunur.
- 3D kamera seçenekleri dropdown'a taşındı.
- 3D üst kamera presetleri gerçek state üzerinden çalışır.
- Alttaki heatmap butonları artık 3D layer butonlarıyla çakışmaz.
- 3D sahnedeki araç/arabamsı aktif rota objesi render edilmez.
- Layout Architect içindeki 3D Editor artık düz 2D blok değil, gerçek WebGL digital twin sahnesidir.
- TR / EN / DE / AR dictionary güçlendirildi.
- Command Center içindeki Optimum plan üret butonu gerçek plan üretme akışına bağlandı.
- NPM registry sorunu için frontend `.npmrc` eklendi.

### Backend
- `main.py` pakete eklendi; artık sadece `main_recovered.py` yok.
- `engine.py`, `dxf_parser_smart.py`, `master_products_api.py`, `storage.py`, `overrides.py`, `auth_routes.py` pakete dahil edildi.
- `/upload-products-csv` CSV ve XLSX destekler.
- `/parse-layout-file` DXF ve JSON destekler; DXF için smart parser kullanır.
- `/generate-planogram-council` eklendi.
- `ai_planogram_engine.py` pakete dahil edildi, ancak API boot etmek için torch zorunlu değildir.
- Production-safe `ai_council_bridge.py` eklendi: satış, storage, ergonomi, marka/kategori, facing/depth ve refill mantığıyla deterministic Council planı üretir.

## Kurulum

### Frontend
```bash
cd C:\Users\ErdiAydın\planai\frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

Eğer npm hâlâ eski internal registry'ye gitmeye çalışırsa:
```bash
npm config delete proxy
npm config delete https-proxy
npm cache clean --force
npm config set registry https://registry.npmjs.org/
npm install
```

### Backend
```bash
cd C:\Users\ErdiAydın\planai\backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Dosya yerleşimi
- ZIP içindeki `frontend` klasörünü mevcut `frontend` üzerine kopyala.
- ZIP içindeki `backend` klasöründeki dosyaları mevcut `backend` içine kopyala.
- Önce backend'i, sonra frontend'i çalıştır.

## Net not
Bu sürümde Council'in verdiği RL engine POC pakette duruyor; ama production endpoint torch'a bağımlı değil. Doğru karar bu: önce çalışan ve kırılmayan deterministic Council layer, sonra gerçek store data ile RL fine-tune.
