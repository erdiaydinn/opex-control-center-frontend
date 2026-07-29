# Planogram capacity rebuild — V1

Tarih: 2026-07-29

## Bulgular

Ekli planogram export dosyası 1.030 satır içeriyor; “1.600 SKU” iddiası bu dosyada doğrulanamıyor. Gerçek 1.600 SKU kataloğu ayrı bir test girdisi olarak çalıştırılmalı.

1.030 satırlık export üzerinde:

- 1.016 SKU yerleşti.
- 14 SKU açıkça unplaced döndü.
- 14 kaydın nedeni CHILLED kapasitesinin yetersiz olmasıydı.
- Strict kural ihlali: 0.
- İsim, marka, kategori ve storage alanlarında eksik kayıt: 0.
- CHILLED kapasite kullanımı: %95,04.
- AMBIENT kapasite kullanımı: %28,31.
- FROZEN kapasite kullanımı: %79,20.

Bu sonuç “her SKU rafa zorla kondu” anlamına gelmez. Motor kapasite yetmediğinde ürünü saklamaz; nedeni ile birlikte unplaced listesine çıkarır.

## Beypazarı gözlemi

Beypazarı Coala gibi 6 x 200 ml ürünler çoklu içecek fiziksel profiline normalize edilir. Varsayılan facing isteği genişlik bazında beş ile sınırlandırılır; gerçek raf genişliği yetmiyorsa fit_facing bunu daha da düşürür. Böylece tek ürünün ilk rafa bütün genişliği tüketmesi engellenir.

Bu yine ürünün gerçek master ölçüsünün yerini tutmaz. Üretim kataloğunda genişlik, yükseklik, derinlik, ambalaj tipi, kasa içi adet ve görsel doğrulanmalıdır.

## Sonraki kabul kapıları

- Gerçek 1.600 SKU dosyasını aynı endpoint ile çalıştırıp storage bazında kapasite raporu almak.
- Tahmini ölçüleri master ölçülerle değiştirmek; tahminli kayıtları yayına kapatmak.
- CHILLED fixture sayısı ve raf genişliği için Store DNA kapasite revizyonu yapmak.
- İçecek, donuk, soğuk zincir, kasa-pack ve temizlik ayrımı için senaryo değerlendirme seti eklemek.
- Plan versiyonu, yayın onayı ve geri alma akışını veritabanına taşımak.
