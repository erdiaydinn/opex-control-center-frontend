# PLONAGRAM OS V1.9.2 — Classification Pipeline Patch

ABC upload ve Catalog merge hattına V1.9.1 classification guard bağlanır.

Ana kural:

```text
ABC = görsel + stok + %orders + %stops + ABC + rank
Catalog = ölçü + storage + ağırlık + case pack
Location = sadece delta için mevcut lokasyon
Engine = hedef lokasyonu belirler
```

## Kurulum

```powershell
robocopy "C:\Users\ErdiAydın\Downloads\PLONAGRAM_OS_V1_9_2_CLASSIFICATION_PIPELINE_PATCH\backend" "C:\Users\ErdiAydın\planai\backend" /E /XD data database __pycache__ .git /XF *.pyc
```

## Test

```powershell
cd C:\Users\ErdiAydın\planai\backend
python .\tests\test_v192_classification_pipeline.py
```

Beklenen:

```text
✅ V1.9.2 classification pipeline integration tests passed
```

## Test edilen kararlar

- Shopping Bag %Orders çok yüksek olsa bile engine'e gitmez.
- Coca-Cola gibi gerçek ürün sellable_products içine gider.
- ABC Product Image URL, visual_source=abc_upload olarak korunur.
- Ramazan Pidesi La Lorraine yazmasa bile bakery review'a düşer.
- Algida storage conflict durumunda catalog FROZEN korunur, ABC AMBIENT sadece hint olarak loglanır.
