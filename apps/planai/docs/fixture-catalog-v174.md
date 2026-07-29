# Fixture Catalog v1.7.4

V1.7.4 fixture catalog backend/services/fixture_catalog.py içindedir.

Temel kural: storage_class fiziksel/sıcaklık kısıtıdır; merch_group komşuluk/merchandising kısıtıdır.

Örnek:

```text
Domestos:
storage_class = AMBIENT
merch_group = NON_FOOD_ODOR
```

Yani ambient rafa girebilir, ama gıda ile aynı rafta duramaz.

