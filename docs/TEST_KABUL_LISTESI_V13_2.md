# OPEX Workforce V13.2 yerel pilot kabul listesi

Önce çalıştırın:

```powershell
.\PREPARE_OPEX_TEST_V13_2.ps1
```

Script başarılı olmadan fonksiyon testine geçmeyin. Test öncesi PostgreSQL yedeği
`test-artifacts` klasörüne alınır.

## P0 — testi durduran kontroller

- [ ] `http://localhost:8080/workforce` açılıyor.
- [ ] `erdi.aydin@yemeksepeti.com` ve boş olmayan pilot şifreyle giriş yapılabiliyor.
- [ ] Dashboard, Vardiya Planı, Onay Akışı, Depo ve Konum, Kural Setleri açılıyor.
- [ ] Sayfa yenilendiğinde oluşturulan kayıtlar PostgreSQL'den geri geliyor.
- [ ] Kullanıcı rolü dışında kalan manuel düzeltme ve TC görüntüleme işlemi engelleniyor.

## Yönetici akışı

- [ ] Tek vardiya oluşturuluyor; vardiyasız kişi check-in yapamıyor.
- [ ] Toplu vardiya yükleme aynı kaydı ikinci kez oluşturmuyor.
- [ ] Depo koordinatı/yıçapı düzenleniyor ve audit log'a yazılıyor.
- [ ] Kural değişikliğinde effective date ve eski/yeni değer audit log'da görülüyor.
- [ ] İzin talebi yönetici görevine düşüyor; onay/red ve gerekçe picker'a dönüyor.
- [ ] Eksik/fazla mesai tekil ve toplu onaylanabiliyor.
- [ ] Kişi/depo puantajı ve dönem bordro dosyası ondalık saatle indiriliyor.

## Picker yerel pilot akışı

- [ ] Picker ekranı varsayılan `100184` personelini ve bugünkü vardiyayı gösteriyor.
- [ ] Check-in, yalnız Yerel Pilot modunda atanmış depo koordinatı ve `DEVICE-1` ile simüle ediliyor.
- [ ] Audit kaydında `pilot_simulation=true` görülüyor.
- [ ] Molaya çıkınca düğme anında **Molayı Bitir** oluyor ve kronometre ilerliyor.
- [ ] Molayı bitirip vardiyayı kapatma çalışıyor.
- [ ] İtiraz/düzeltme ve izin talebi yönetici görevlerine düşüyor.
- [ ] Bildirim okundu/sil/tümünü sil ve arşiv çalışıyor.

## Mobil görünüm

- [ ] Aynı Wi-Fi'daki telefonda scriptin verdiği `http://IP:8080/workforce/app` adresi açılıyor.
- [ ] 320–430 px genişlikte yatay taşma, üst üste binme veya görünmeyen buton yok.
- [ ] Türkçe, İngilizce, Almanca ve Arapça/RTL temel ekranlarda kontrol edildi.
- [ ] Açık ve koyu temada form, tablo, modal ve durum etiketleri okunuyor.

LAN/HTTP telefon kontrolü gerçek PWA kurulumu, App Attest/Play Integrity, güvenilir GPS,
APNs/FCM veya Dynamic Island testi değildir. Bunlar native ve HTTPS aşamasında ayrıca yapılır.

## Hata teslimi

Hata oluştuğunda önce ekran görüntüsü, saat, kullanıcı, ekran ve yapılan son işlemi not edin;
ardından:

```powershell
.\COLLECT_OPEX_TEST_DIAGNOSTICS_V13_2.ps1
```

Oluşan `test-artifacts\diagnostics-*.zip` dosyasını paylaşmadan önce içeriğini kontrol edin.
Script `.env`, TC/personel tabloları ve push anahtarlarını pakete eklemez.
