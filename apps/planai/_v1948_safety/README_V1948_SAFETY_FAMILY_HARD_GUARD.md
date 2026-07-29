# V1.9.48 Safety Family Hard Guard

Bu patch planogramAllocator ve planogramAllocatorV2 içinde safety-family hard guard uygular.

## Ne düzeltir
- Gıda / gıda dışı aynı rafta yerleşemez.
- Gıda / gıda dışı aynı modülde yerleşemez.
- Gıda / gıda dışı yan modül temasında yerleşemez.
- Yumoş, Perwoll, Persil, Bref, Asperox, Koroplast, Selpak, Maylo, Orkid, Varta, Bic, Purina, Felix vb. ürünler FOOD gibi yanlış sınıflanmaz.
- Brand/kategori/manual rule bu güvenlik kararını ezemez.

## Dikkat
Eğer non-food için layoutta yeterli H/I/STEEL_RACK/G/F alanı yoksa bazı ürünler atanamayana düşebilir. Bu doğru davranıştır; kalite riskli karışık yerleşimden daha iyidir.
