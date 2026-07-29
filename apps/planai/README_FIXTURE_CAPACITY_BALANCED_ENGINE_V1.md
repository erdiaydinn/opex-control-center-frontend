# PLONAGRAM Fixture Capacity + Balanced Engine V1

Bu patch iki ana problemi hedefler:

1. **CHILLED/FROZEN ürünler için uygun fixture yok** problemi
   - Soğuk oda / donuk oda / Algida / yatay dolap gibi objeler artık sadece dekor değil.
   - Layout objeleri ürün yerleşebilir shelf capacity'ye çevrilir.
   - Layout'ta +4 / -18 kapasite azsa AI capacity aisle eklenir.

2. **C modülü ve sonrası boş kalıyor** problemi
   - Eski engine ilk 40 candidate shelf ile sınırlı kalabiliyordu.
   - Yeni placement tüm uygun rafları değerlendirir.
   - Boş modül / düşük doluluk / C-D-E-F sonrası koridorlara balance bonusu verir.
   - A/B modülleri belli seviyeden sonra tüm ürünleri yutamaz.

## Kurulum

Backend klasöründe:

```bat
cd C:\Users\ErdiAydın\planai\backend
venv\Scripts\activate
copy engine.py engine_before_fixture_capacity_balanced_v1.py
```

ZIP içindeki şu dosyaları backend klasörüne kopyala:

```txt
backend/fixture_capacity_mapper.py
backend/apply_fixture_capacity_balanced_patch_v1.py
backend/smoke_test_balanced_engine.py
```

Patch'i çalıştır:

```bat
python apply_fixture_capacity_balanced_patch_v1.py
```

8001 portu doluysa:

```bat
for /f "tokens=5" %a in ('netstat -ano ^| findstr :8001') do taskkill /PID %a /F
```

Backend:

```bat
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## Test

```bat
python smoke_test_balanced_engine.py
```

Beklenen:
- AMBIENT, CHILLED, FROZEN ürünler yerleşir.
- placed_by_aisle sadece A/B değil, C/D/E/F ve AI cold/frozen capacity alanlarını da gösterir.
- `engine_patches` içinde `fixture_capacity_balanced_engine_v1` görünür.

## Not

Bu patch frontend'i bozmaz. Backend engine davranışını düzeltir.
2D ekranda C ve sonrası boş kalma problemini azaltmak için planogramı yeniden üretmen gerekir.
