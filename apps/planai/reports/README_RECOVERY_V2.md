# PLONAGRAM OS RECOVERY BASELINE V2

Bu paket V1'in görsel/mimari eksiklerini düzeltmek için hazırlandı. Öncelik: eski hotfix çorbasına dönmeden, çalışan ve genişletilebilir tek baseline.

## V2'de düzeltilen ana başlıklar

- PLONAGRAM monogramı yeniden çizildi; F gibi görünen logo kaldırıldı.
- Loading ekranı tekrar hareketli çizgisel logo animasyonuna döndü.
- Command Center ve mini digital twin boş placeholder olmaktan çıkarıldı.
- Live 3D ekranına raf modülleri, zone blokları, kolonlar, dispatch, receiving, Algida, rota, pulse ve heatmap katmanları eklendi.
- 3D tam ekran butonu eklendi.
- 3D mouse drag/pan ve wheel zoom eklendi.
- Kamera presetleri çalışır: Overview, Top, +4 Soğuk, -18 Donuk, Dispatch.
- SKU arama kamerayı ilgili storage zone'a odaklar ve sağ paneli günceller.
- Layout Architect artık hem 2D hem 3D Editor modunda çalışır.
- Nesne kataloğu genişletildi: koridor, raf modülü, kolon, duvar, +4 oda, -18 oda, Algida dolabı, yatay dolap, dispatch, mal kabul, elektrik panosu, acil çıkış, dinlenme alanı, tuvalet, müdür masası, transpalet.
- Layout nesneleri seçilebilir, taşınabilir, property panelinden ölçü/zone/modül/raf değiştirilebilir.
- En iyi yerleşimi öner, kaydet, kopyala, sil butonları çalışır.
- Ürün Yerleşimi ekranına ürün görselleri, facing/depth butonları ve büyük raf iç düzenleme popup'ı eklendi.
- Raf popup içinde ürün ata, satışa/markaya göre sırala, facing/depth değiştir, raf/modül yazdır ve JSON export var.
- Planogram ekranında raflara tıklanınca aynı büyük popup açılır.
- Heatmap modu çalışır: satış, refill, cold chain görünümü.
- Görev ekranında kullanıcıya görev atanır, admin yanıtı/status girilir.
- Fotoğraf kanıt ekranı eklendi.
- Admin ekranında tüm depolar/depo bazlı görünüm, ambient/chilled/frozen doluluk, yeri değişecek ürün sayısı ve modül/raf doluluk tablosu var.
- Topbar SKU/Layout upload ve optimum plan üret butonları artık state aksiyonu verir.

## Kurulum

1. Mevcut frontend'i yedekle.

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BROKEN_BACKUP /E /I /H
```

2. `frontend` klasörünü bu paketteki `frontend` ile değiştir.

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm install
npm run dev
```

3. Backend'i değiştirmek istersen `backend/main_recovered.py` dosyasını mevcut `backend/main.py` olarak kopyala. Mevcut çalışan backend varsa zorunlu değil.

```bash
cd C:\Users\ErdiAydın\planai\backend
copy main.py main_BROKEN_BACKUP.py
copy main_recovered.py main.py
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Net not

Bu V2 gerçek WebGL/Three.js motorunun yerine geçmez; ama önceki V1 gibi boş placeholder kalmaz. 3D sahne, fullscreen, mouse hareketi, kamera presetleri ve editör akışları çalışan recovery baseline'dır. Bundan sonraki sprint Three.js mesh motoru olmalı.
