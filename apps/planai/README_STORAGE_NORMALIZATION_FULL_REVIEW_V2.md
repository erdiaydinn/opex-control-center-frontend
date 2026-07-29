# PLONAGRAM Storage Normalization Full Review V2

Bu paket Beypazarı tekil düzeltmesi değildir. Yüklediğin `plonagram_unplaced_diagnostics.csv` dosyasındaki 5,881 satır incelenerek hazırlandı.

## İnceleme sonucu
- İncelenen satır: 5,881
- Storage önerisi değişen satır: 1,350

Crosstab:
suggested_storage_type  AMBIENT  CHILLED  FROZEN
storage_type                                    
AMBIENT                    3456      161       7
CHILLED                    1178      814       4
FROZEN                        0        0     261

## Kurulum
```bat
cd C:\Users\ErdiAydın\planai\backend
venv\Scripts\activate
```

ZIP içindeki `backend` dosyalarını backend klasörüne kopyala.

Önce kodu bağla:
```bat
python apply_storage_normalizer_code_patch_v2.py
```

Sonra master ürün dosyalarını düzelt:
```bat
python fix_master_storage_full_review_v2.py
```

Backend'i yeniden başlat:
```bat
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## Rapor
`reports/plonagram_storage_review_suggestions.csv` içinde her satır için:
- eski storage_type
- suggested_storage_type
- storage_fix_reason
- storage_changed

alanları var.
