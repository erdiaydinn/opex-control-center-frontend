# PLONAGRAM OS V1.7.7 — True Twin Finishing Pass

Bu patch V1.7.6 üzerine gelen 3D ince işçilik paketidir. Backend, Store DNA, ABC/catalog ve physics engine tarafına dokunmaz.

## Amaç

3D ekranın “blok çizim” hissini azaltıp gerçek depo / raf dili kazandırmak:

- Daha gerçekçi raf gövdeleri
- Metal dikme + çapraz gergi hissi
- Raf içi kutu / ürün yoğunluğu
- Depo kabuğu, arka duvar, pencere/truss ve zemin rota çizgileri
- Ürün görsel URL’lerinin sahnede yazı gibi taşmasını engelleme
- URL varsa küçük ürün görseli, yoksa temiz ikon gösterimi
- 3D mimari editörde daha ferah çalışma alanı

## Güncellenen dosyalar

- `frontend/src/components/Live3D/TwinStudio3D.jsx`
- `frontend/src/components/Live3D/TwinStudio3D.css`
- `frontend/src/styles/components.css`
- `frontend/src/components/LayoutArchitect.jsx` *(V1.7.6 içeriği korunur)*

## Kurulum

```powershell
robocopy C:\Users\ErdiAydın\Downloads\v177\frontend C:\Users\ErdiAydın\planai\frontend /E /XD node_modules dist
```

Sonra:

```powershell
cd C:\Users\ErdiAydın\planai\frontend
npm run dev -- --host 0.0.0.0 --port 5174
```

OPEX bridge için ayrıca:

```powershell
cd C:\Users\ErdiAydın\opex-control-center-scaffold\frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

## Kontrol listesi

1. `http://localhost:5174` direkt açılmalı.
2. `http://localhost:5173/planogram` içinde iframe ile görünmeli.
3. 3D sahnede ürün image URL metni görünmemeli.
4. Raflar artık sadece pembe transparan blok gibi kalmamalı; dikme, raf, paket ve çapraz detay görünmeli.
5. Mimari Düzenleyici > 3D Editor ekranında canvas daha ferah olmalı.

## Not

Bu hâlâ final asset pipeline değildir. Bir sonraki doğru adım gerçek fixture model katalogudur:

- regular_rack glTF
- algida_fridge glTF
- horizontal_chiller glTF
- produce_crate glTF
- receiving room / wall / door primitives
- SKU image atlas / texture cache

