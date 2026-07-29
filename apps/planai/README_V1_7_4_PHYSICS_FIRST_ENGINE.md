# PLONAGRAM OS V1.7.4 — Physics-First Engine Patch

Bu paket görsel makyaj paketi değildir. Amaç: Planogram Studio'nun sahada yanlış plan üretmesini engelleyen fiziksel/operasyonel omurgayı kurmak.

## Ana karar

- 3D Studio vitrin; engine gerçeklik kaynağıdır.
- Store DNA source of truth'tur.
- Kullanıcı catalog yüklemez; catalog gömülü sistem datasıdır.
- ABC kullanıcı inputudur.
- Storage mismatch hard reject'tir.
- Fiziksel sığmayan ürün yerleşmez.
- Atanamayan ürün raporu zorunludur.

## Eklenen / değişen backend dosyaları

```text
backend/services/fixture_catalog.py
backend/services/product_classifier.py
backend/services/fixture_pool_builder.py
backend/services/physical_capacity_engine.py
backend/services/unplaced_report.py
backend/services/planogram_engine.py
backend/services/store_dna_service.py
backend/v17_routes.py
backend/test_physics_engine_v174.py
```

## Eklenen / değişen frontend dosyaları

```text
frontend/src/components/StoreDNA/StoreDNASetupWizard.jsx
frontend/src/utils/planogramAllocator.js
frontend/src/styles/components.css
```

## Neyi çözer?

### 1. 100 cm raf fiziksel olarak 100 cm kabul edilir

```text
max_possible_facing = floor(remaining_width_cm / product_width_cm)
final_facing = min(demand_based_facing, max_possible_facing)
```

Örnek:

```text
100 cm raf / 8 cm ürün  => max 12 facing
100 cm raf / 20 cm ürün => max 5 facing
100 cm raf / 130 cm ürün => unplaced: PRODUCT_TOO_WIDE_FOR_SHELF
```

### 2. Storage class hard match

```text
ICE_CREAM  => ALGIDA_FREEZER
CHILLED    => MARTEK_CHILLED / CHILLED_ROOM
FROZEN     => MARTEK_FROZEN / FROZEN_ROOM / HORIZONTAL_FREEZER
FRESH_PRODUCE_AMBIENT => PRODUCE_AMBIENT_SHELF
FRESH_PRODUCE_CHILLED => PRODUCE_CHILLED_SHELF
AMBIENT    => REGULAR_AMBIENT_RACK / NEW_GEN_STEEL_RACK
```

### 3. Deterjan kuralı düzeltildi

Deterjan ambient'tir; ambient rafa girebilir. Ama gıda ile aynı rafta yan yana duramaz.

```text
storage_class = AMBIENT
merch_group = NON_FOOD_ODOR
```

### 4. Store DNA Wizard checkbox yerine adet input'a geçti

Özel ekipmanlar artık var/yok değil adet ile girilir:

```text
Algida dolabı
Martek +4 dolap
Martek -18 dolap
Yatay donuk dolap
Meyve-sebze kasa rafı
Yeşillik +8 rafı
Yeni nesil çelik raf
```

### 5. Fixture pool builder artık shelf-level slot üretir

Her slot şu bilgileri taşır:

```text
slot_id
fixture_instance_id
fixture_key
aisle_id
module_id
shelf_no
shelf_width_cm
shelf_depth_cm
shelf_height_cm
remaining_width_cm
storage_classes
brand_lock
hard_rules
```

### 6. Atanamayan raporu structured hale geldi

Her ürün için:

```text
sku
product_name
brand
storage_class
merch_group
reason_code
human_action
suggested_action
required_width_cm
available_width_cm
missing_fixture_type
```

## Test

Backend içinde:

```bash
cd C:\Users\ErdiAydın\planai\backend
python test_physics_engine_v174.py
```

Beklenen:

```text
✓ test_100cm_shelf_20cm_product_max_5_facing
✓ test_100cm_shelf_8cm_product_max_12_facing
✓ test_algida_goes_to_algida_fixture
✓ test_algida_never_goes_to_ambient_without_ice_cream_fixture
✓ test_chilled_never_goes_to_frozen_or_ambient
✓ test_deterjan_ambient_but_not_next_to_food_same_shelf
✓ test_produce_needs_produce_fixture
✓ test_too_wide_product_unplaced
✅ V1.7.4 physics-first engine tests passed
```

## Kurulum

### Güvenli kopyalama

Database klasörünü kopyalama. Mevcut DB korunmalı.

```powershell
robocopy C:\Users\ErdiAydın\Downloads\v174\backend C:\Users\ErdiAydın\planai\backend /E /XD database __pycache__ /XF *.pyc
robocopy C:\Users\ErdiAydın\Downloads\v174\frontend C:\Users\ErdiAydın\planai\frontend /E /XD node_modules dist
```

### Backend

```powershell
cd C:\Users\ErdiAydın\planai\backend
python -m pip install -r requirements.txt -i https://pypi.org/simple
python test_physics_engine_v174.py
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

### Frontend

```powershell
cd C:\Users\ErdiAydın\planai\frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5174
```

## Yeni endpointler / değişen davranış

```text
GET /fixture-catalog
GET /stores/{store_code}/dna/fixture-pools
POST /planograms/{store_code}/generate-fixture-first
GET /unplaced/{store_code}/{version_id}/csv
GET /unplaced/{store_code}/{version_id}/xlsx
```

## Acceptance criteria

Bu paket ancak şu testler geçtiyse kabul edilir:

```text
- 100 cm raf 100 cm gibi davranıyor.
- 8 cm ürün 12 facing üstüne çıkmıyor.
- 20 cm ürün 5 facing üstüne çıkmıyor.
- 130 cm ürün 100 cm rafa girmiyor.
- Algida ambient'e düşmüyor.
- Chilled ürün frozen/ambient'e düşmüyor.
- Produce fixture yoksa patates/yeşillik sessizce ambient rafa basılmıyor.
- Deterjan ambient kabul ediliyor ama gıda ile aynı shelf'e konmuyor.
- Unplaced report reason_code + human_action veriyor.
```

## Bilinen sınırlar

- Bu patch PDF/Excel saha çıktı tasarımını büyütmez; sadece unplaced CSV/XLSX export'u güçlendirir.
- 3D görsel benchmark ayrı sprinttir. Bu paket 3D'yi engine state mirror olarak besleyecek temeli kurar.
- Gerçek Fulya/Anka/Güven FR Store DNA ölçüleri girildikçe fixture override yapılmalıdır.

