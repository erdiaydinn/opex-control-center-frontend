# PLONAGRAM OS Recovery v1.5

Bu sürüm mockup/resim paketi değil; çalışan kod paketidir. v1.4 üstüne sorun kapatan recovery sürümüdür.

## Kapatılan problemler

1. **Komuta Merkezi yazı/hero çakışması**
   - Sidebar genişliği artırıldı.
   - Menü yazıları taşmayacak şekilde kırılır.
   - Hero alanı daha dengeli grid yapısına alındı.
   - Live Digital Twin önizlemesine küçük `Kamera değiştir` aksiyonu eklendi.

2. **Canlı 3D kamera karmaşası**
   - 3D sahne içindeki üst kamera dropdown kaldırıldı.
   - Kamera yönetimi yalnızca sağ paneldeki `KAMERA` kartında.
   - Preset dropdown + hızlı preset butonları var.
   - Kamera yardım kartı sahnenin sağ altında kompakt gösterilir.

3. **3D sahne buton/katman çakışması**
   - Üst katman butonları sahnenin üstüne, heatmap filtreleri alta ayrıldı.
   - Alt butonların sahne/yardım kartı altında kalması engellendi.

4. **Mimari Düzenleyici 3D editör**
   - Ekran artık varsayılan olarak `3D Editor` açılır.
   - Kolonlar, odalar, receiving, dispatch ve raf objeleri tıklanabilir.
   - Seçili obje sağ panelde düzenlenir.
   - `Mouse ile taşı` modu eklendi: mod açılınca 3D objeyi sürükleyerek x/y pozisyonu değiştirilebilir.
   - Sağ panele nudge okları eklendi.

5. **SKU / CSV / XLSX yükleme**
   - `upload-products-csv` endpoint adı korunur ama CSV + XLSX okur.
   - Frontend CSV fallback korunur.
   - Loading overlay iptal edilebilir şekilde çalışır.

6. **Ürün yerleşimi / A-B-C koridorlarının boş kalması**
   - Local Store Plan Allocator v1.5 güncellendi.
   - Plan artık mevcut Store DNA / fixture state üzerinden yerleşir.
   - A/B/C koridorları hızlı ve A sınıf ürünlerle dengeli doldurulur.
   - Ağır ürünler ve su gibi hacimli ürünler arka/çelik raflara atılır.
   - Domestos/deterjan gibi koku riski olan non-food ürünler gıda ön koridorlarından uzak tutulur.
   - Patates, muz, mandalina gibi ürünler random ambient rafa değil meyve-sebze rafı önceliğine gider.
   - Maydanoz/marul gibi soğukta durması gereken ürünler +4 mantığına alınır.

7. **Atanamayan ürün raporu**
   - `Atanamayanlar` tabına `CSV indir` ve `Excel indir` butonları eklendi.
   - Ekranda ilk 300 satır gösterilir, export tüm kayıtları indirir.

8. **3D performans / karmaşa**
   - Canlı 3D sahnede ürün marker sayısı 1200 ile sınırlandı; planogram datası tam kalır.
   - Komuta Merkezi mini twin zaten düşük yoğunlukta render edilir.

## Kurulum

### Frontend

```bash
cd C:\Users\ErdiAydın\planai\frontend
```

Mevcut frontend klasörünü yedekle. Sonra ZIP içindeki `frontend` klasörünü bu klasörün üzerine kopyala.

```bash
npm install
npm run dev
```

NPM registry timeout alırsan:

```bash
npm config set registry https://registry.npmjs.org/
npm cache clean --force
npm install --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
npm run dev
```

### Backend

```bash
cd C:\Users\ErdiAydın\planai\backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Test akışı

1. Backend'i başlat.
2. Frontend'i başlat.
3. `SKU yükle` ile `Fulya Abc rapor.csv` veya Excel dosyasını yükle.
4. Loading ekranında iptal butonunu test et.
5. `Optimum plan üret` butonuna bas.
6. Planogram ekranında A/B/C koridorlarının dolduğunu kontrol et.
7. `Atanamayanlar` tabında CSV/Excel indirmeyi test et.
8. `Canlı 3D` ekranında kamera presetlerini sağ panelden dene.
9. `Mimari Düzenleyici` ekranında `Mouse ile taşı` modunu açıp kolon/alan sürükle.

## Kritik not

Bu sürüm hâlâ kalıcı veritabanı değil, frontend state + backend endpoint tabanlı recovery sürümüdür. Pazar lideri seviyede sonraki zorunlu adım: Store DNA ve planogram versiyonlarını SQLite/Postgres gibi kalıcı bir veri katmanına almak.
