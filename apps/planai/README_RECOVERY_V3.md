# PLONAGRAM OS Recovery Baseline V3

Bu sürüm V1/V2 üzerine görsel makyaj değil; kullanıcının işaretlediği kritik eksikleri toparlayan recovery sürümüdür.

## V3 ile gelen ana düzeltmeler

- Command Center üzerindeki 1/2 numaralı boş dijital ikiz alanları daha dolu, zone/rota/raf/ürün içeren operasyon preview'a çevrildi.
- Canlı 3D ekranında alan seçimi için dropdown eklendi.
- Seçili alanda doluluk, modül sayısı, raf sayısı ve yeri değişecek ürün sayısı artırma/azaltma ile değişir.
- 3D mouse drag/pan ve wheel zoom korunur, tam ekran davranışı güçlendirildi.
- 3D sahne daha fazla raf, zone, akış, kolon, cold-flow ve route efekti içerir.
- Ürün Yerleşimi ekranına koridor/modül/raf dropdown seçicileri eklendi.
- Kural Motoru artık ağırlık motoru içerir: satış, kategori, marka, refill, rota, soğuk zincir ağırlıkları.
- Council High Intelligence Repository kartı eklendi; ağırlık değiştikçe karar yorumu, skor/refill/risk/güven etkisi değişir.
- Delta Planogram Türkçe neden/öncelik açıklamalarıyla genişletildi.
- Yayınlama ekranı basit karttan çıkarıldı; depo bazlı yayınlama kontrol kulesi ve blokaj nedeni eklendi.
- Fotoğraf Kanıtı göreve bağlandı; kanıt kaydı görevi kapatabilir.
- Raporlar executive/architect ayrımına hazırlandı; karar matrisi ve Council yorumu eklendi.
- Admin paneli genişledi: depo görünümü, kullanıcı yönetimi, rol/title değiştirme, kullanıcı ekle/sil, onay merkezi, duyuru yayınlama.
- Türkçe dildeki bariz İngilizce kalan alanlar azaltıldı.

## Kurulum

```bash
cd C:\Users\ErdiAydın\planai
xcopy frontend frontend_BACKUP_BEFORE_V3 /E /I /H
```

ZIP içindeki `frontend` klasörünü mevcut `frontend` üzerine kopyala.

```bash
cd C:\Users\ErdiAydın\planai\frontend
npm install
npm run dev
```

## Not

Bu hâlâ recovery baseline'dır. Gerçek piyasa lideri 3D için bir sonraki sprintte CSS 3D sahne yerine Three.js/WebGL mesh motoruna geçilmelidir. V3 amacı: çöken sistemi tekrar çalışır, daha kapsamlı ve daha az mock görünümlü hale getirmektir.
