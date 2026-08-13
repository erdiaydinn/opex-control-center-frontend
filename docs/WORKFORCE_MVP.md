# OPEX Workforce Live v12.9

## V12.9 profesyonel picker ana ekranı ve serbest açıklama

- Mobil ana ekran canlı vardiya, depo, rol, saat, check-in/mola durumu, kayıtlı cihaz ve ana vardiya aksiyonunu tek güçlü kartta toplar.
- Aylık vardiya, tamamlanan vardiya ve açık talep KPI'ları ile arşiv, izin, bildirim ve görevler için 2×2 hızlı işlem alanı eklenmiştir.
- Ana ekrandaki yönetim paneline dönüş oku kaldırılmış, yerine OPEX Workforce uygulama başlığı getirilmiştir.
- İzin/itiraz açıklaması, yönetici kararı, cihaz sıfırlama ve manuel düzeltme gerekçelerinde minimum karakter sınırı kaldırılmıştır. Alan zorunluysa boş bırakılamaz; tek karakter kabul edilir.
- Backend şemaları aynı kuralla güncellenmiş ve tek karakterli açıklamanın kabul edildiğini doğrulayan otomatik test eklenmiştir.

## V12.8 anlık mola, kronometre ve izin talebi düzeltmesi

- `Molaya Çık` işleminden sonra aynı ekranda anında `Molayı Bitir` görünür. React'in canlı metin düğümünü yeniden kullanmasıyla çeviri katmanının eski etiketi geri yazması giderildi.
- Aktif mola, vardiya detayında ve `Bildirimler` ekranında saniyelik kronometreyle gösterilir; sayfa yenileme veya uygulama içinde gezinme mola durumunu kaybettirmez.
- Uygulama PWA manifesti ve servis çalışanı içerir. Bildirim izni verilen destekli cihazlarda aktif mola bildirimi ekranda kalır ve dokununca uygulama açılır.
- Native iOS kabuğu için `window.webkit.messageHandlers.opexLiveActivity` köprüsü `start`/`finish`, vardiya, depo, kişi ve başlangıç zamanını iletir. Dynamic Island/ActivityKit gösterimi native iOS hedefinde bu köprüye bağlanmalıdır.
- İzin talebi doğrulaması sessizce durmaz; hatayı ekranda gösterir, açıklamayı en az 3 karakterle kabul eder, mükerrer açık talebi engeller ve başarılı gönderimde picker bildirimi üretir.

## V12.6 itiraz, yönetici görevleri ve bildirim merkezi

- Picker vardiya detayındaki `İtiraz / Düzeltme Talebi` çalışan bir formdur; talep, mobilde durum takibine ve PC yönetici kuyruğuna düşer.
- `Yönetici Görevleri` ekranı 11 saat roster görevlerini ve picker düzeltme taleplerini birleştirir. Hedef süre veya giriş/çıkış değerleri gerekçeli olarak düzeltilebilir.
- Aynı yönetici kuyruğu mobil uygulamadaki `Görevler` sekmesinde görünür ve yetkili yönetici telefondan sonuçlandırabilir.
- `Duyuru ve Bildirimler` alanı tüm kullanıcı, depo veya tek personel hedefli duyuru yayınlar.
- Vardiya yayınlandığında bildirim; vardiya başlangıç/bitişinden ayarlanabilir dakika önce check-in/check-out hatırlatması planlanır.
- `Kullanıcılar` ekranında tekil personel düzenleme; TC yetkisi, e-posta, telefon, Actual Warehouse, İK kodu, unvan, işe giriş ve işten ayrılış alanlarını kapsar.
- Backend düzeltme talepleri, yönetici görevleri, duyurular, bildirim politikası ve zamanlanmış bildirim endpoint'leri ile aynı audit modeline bağlandı.

## V12.5 audit, sürümlü kural ve güvenli cihaz yenileme

- 11 saat istisna Excel'i ile tüm dönem mesai Excel'i birbirinden ayrıldı.
- Audit Log ekranı ve sunucuda hash zincirli audit endpoint'i eklendi.
- Kural türü seçilerek oluşturulan her tarihli sürüm ilgili hesabı veya blokajı etkiler.
- Tek aktif cihaz modeli, eski cihazı iptal eden sıfırlama ve yeni cihaz kayıt endpoint'leri eklendi.
- Audit veritabanı Docker kurulumunda kalıcı `dockos-state` volume'ünde tutulur. Tablo `UPDATE` ve `DELETE` işlemlerini trigger ile reddeder; her kayıt önceki hash'i taşır.
- Hukuki saklama politikası için üretimde bu veritabanı yedeği ayrıca WORM/Object Lock depoya ve güvenilir zaman damgası hizmetine aktarılmalıdır.

## V12.4 TC ile otomatik Roster ID eşleştirme

- Roster kimlik eşleştirme şablonu İK Employee ID istemez; standart dosya formatı `rider_id, rider_name, TCK, contract_name, IsActive, phone_num, email`.
- Sistem `TCK` alanını İK personel ana verisindeki TC ile eşleştirir ve doğru İK Employee ID'yi sonuç olarak üretir.
- TC gelen satırda HR Employee ID veya e-posta yedeğine sessizce düşülmez; böylece yanlış kişiye bağlanma riski azaltılır.
- HR Employee ID / tekil e-posta desteği yalnız eski veya TC'siz istisna dosyalar için yedek olarak korunur.

## V11 İK uyumlu ondalık saat çıktısı

- Kişi Bazlı Mesai Excel'indeki ham net, hesaba esas, normal, resmî tatil, gece, fazla mesai ve izin kolonları dakika yerine sayısal saat üretir.
- Örnekler: 690 dakika `11.5`, 300 dakika `5`, 15 dakika `0.25` olarak yazılır.
- Hücreler metin değildir; Excel toplamı, pivot tablo ve bordro formüllerinde doğrudan kullanılabilir.
- Dönem kapanışı ve puantaj CSV başlıkları da `(saat)` olarak değiştirilmiş ve değerleri ondalık saate çevrilmiştir.

## V10 geçici roster kaynağı ve toplu Roster ID

- Ana ürün ve dönem kapanışı check-in/check-out puantajını kullanır. OPEX Roster Lab, mobil uygulamaya geçiş bitene kadar açılıp kapatılabilen geçici analytics kaynağıdır.
- `Check-in/out’a dön` rosterı silmeden dashboard'u canlı puantaja geçirir. `Geçici verileri sil` yalnız roster satırlarını, kimlik eşleştirmelerini, simülasyonları ve roster görevlerini temizler.
- Personel, izin, depo, staffing norm, check-in/check-out ve audit verileri bu temizlikte korunur.
- `Kullanıcılar` ekranında toplu Roster ID şablonu ve CSV/XLSX yükleme alanı bulunur. `rider_id` ile `TCK` tekil İK personeline bağlanır; isim tek başına eşleştirme yapmaz.
- Toplu yüklenen unvanlar kişi bazlı mesai ve pozisyon filtresinde korunur. Mağaza Müdür Yardımcısı gibi roller raporda görünür; yalnız gerçek müdür rolleri norm hesabı dışında kalır.

## V9 roster–İK kimlik köprüsü

- Roster `personId` ile İK Employee ID farklı olduğunda öncelik TC'dir; İK Employee ID sonuç olarak otomatik bulunur.
- Roster CSV’ye `TCK` kolonu eklenebilir; alternatif olarak `rider_id, rider_name, TCK, contract_name, IsActive, phone_num, email` formatı Kimlik Eşleştirme sekmesine yüklenir.
- İsim benzerliği tek başına otomatik eşleştirme yapmaz. Mükerrer TC/e-posta kayıtları `Belirsiz`, bulunamayanlar `Eşleşmedi` kalır.
- Ham roster ID ve kaynak satır değişmez; hesaplamada İK Employee ID kullanılır. Kişi bazlı tabloda ve Excel’de iki kimlik birlikte gösterilir.
- Time Off kaydı İK Employee ID’de olsa bile farklı roster ID’ye ait vardiya aynı kişi/günde birleşir; izinli gün check-in hatası sayılmaz.

## V8 Workforce Analytics ve kullanıcı yaşam döngüsü

- Ana ekran, veri değiştiren aksiyon içermeyen salt okunur bir Workforce Analytics karar merkezidir.
- Başlangıç/kesim tarihi, Regional Manager, BY/Regional Executive ve depo filtreleri bütün KPI, grafik ve tabloları aynı anda süzer.
- Efektif çalışma, fazla mesai ve oranı, check-in başarısı, norm doluluk, kritik depo, günlük trend, depo/BY sıralaması ve 0-100 iş gücü baskı skoru hesaplanır.
- Baskı skoru norm açığı, fazla mesai yoğunluğu, kayıtsız kişi-gün ve 11 saat anomalilerini birleştirir; norm yeterliyken mesai oluşması ayrı verimlilik kaçağı olarak gösterilir.
- Roster, izin, personel ana veri ve staffing norm birlikte kullanılır; roster yoksa canlı puantaja fallback yapılır. Warehouse Manager ve Rider Captain norm hesabına alınmaz.
- `Kullanıcılar` ana menüsünde Employee ID’ye göre personel upsert, e-posta/TC/işe giriş-çıkış, Actual Warehouse, uygulama hesabı ve erişim durumu tek tabloda yönetilir.
- Excel şablonundaki `Kullanıcı Hesabı=Evet` alanı davetiye oluşturur; seçili kişilere toplu hesap ve şifre sıfırlama bağlantısı üretilebilir, işten çıkan kişinin erişimi kapatılır.

## V7 personel ana veri upsert

- `Dönem Kapanışı > Personel Ana Veri` alanı Employee ID, TC, ad-soyad, işe giriş, işten çıkış, Actual Warehouse, İK depo kodu, unvan, e-posta ve telefonu CSV/XLSX olarak alır.
- Employee ID tekil anahtardır; mevcut kişi tekrar geldiğinde ikinci satır açılmaz, yalnız gelen dolu alanlar mevcut kayda uygulanır.
- Sonradan gelen işten çıkış tarihi mevcut çalışanı günceller ve pasif yapar; boş çıkış alanı daha önceki çıkış bilgisini yanlışlıkla silmez.
- Gönderilen İK depo kod listesindeki 103 sayısal kod doğru raporlama depo adına eşlenir.
- Yükleme özeti yeni, güncellenen, yeni çıkış ve geofence listesinde eşleşmeyen depo sayılarını gösterir; işlem audit kaydı üretir.
- Uygun kolon adlarını içeren doğrudan `.xlsx` şablonu ekrandan indirilir.

## V6 okunabilir çıktı ve yönetici görevleri

- Puantaj baskısı A4 yatayda okunabilir puntoya yükseltildi; çalışan, depo müdürü ve İK için 30 mm yüksekliğinde boş imza kutuları eklendi.
- Yönetim tabloları, depo/kural kartları ve cihaz listelerinde küçük metinler büyütüldü; koyu temada `Düzenle` düğmesinin kart içeriğine taşması giderildi.
- 11 saat istisnaları satır veya toplu seçilebilir; seçilen kayıtlar gerekçeli 7,5 saat simülasyonuna alınabilir.
- Seçilen kayıtlar depoya göre gruplanarak roster’daki Warehouse Manager’a, yoksa BY/Regional Executive’e açık düzeltme görevi olarak atanır.
- Açık görev için aynı roster kaydının ikinci kez atanması engellenir; görev, audit ve yönetici bildirimi üretir.

## V5 OPEX kişi bazlı dönem mesaisi

- OPEX Roster Lab içindeki `Dönem Mesai Hesabı`, seçilen dönemde roster veya izin kaydı bulunan tüm çalışanları listeler.
- Aynı kişinin aynı gündeki roster satırları önce günlük birleştirilir; fazla mesai resmî tatil dakikaları hariç günlük 7,5 saatin üstünden bir kez hesaplanır.
- Ham net, hesaba esas, normal, resmî tatil, yaklaşık gece, fazla mesai, ücretli/ücretsiz izin, izin çakışması ve 11 saat uyarısı ayrı kolonlarda korunur.
- Yüklenen Time Off kayıtları Employee ID + tarih ile roster hesabına bağlanır; izinli gün OPEX çalışmasından düşerken ham roster değeri denetim için saklanır.
- Depo, personel ve unvan filtreleri uygulanmış kişi bazlı dönem sonucu `.xlsx` olarak indirilir.

## V4 arayüz ve depo yönetimi

- Türkçe, İngilizce, Almanca ve Arapça dil tercihi yönetim ve picker ekranlarında kalıcıdır.
- Arapça RTL yerleşim sidebar, tablo, form, modal ve mobil kartları kapsar.
- Koyu tema bütün veri yüzeylerine açık renk/kontrast tanımlar; yazdırma çıktısı beyaz kalır.
- Depolar çoklu seçilerek bölge, geofence, GPS toleransı, doğrulama, QR ve durum alanlarında toplu düzenlenir.
- Toplu işlem boş bırakılan alanları korur ve tek audit olayı üretir.

## V3 dönem kapanışı ve OPEX laboratuvarı

- Kümülatif hesap başlangıç/kesim tarihini ay sınırından bağımsız kullanır.
- Beklenen çalışma yalnız atanmış vardiyadır; işe girişten önce ve çıkıştan sonra süre üretilmez.
- İK çıktısı Employee ID, yetkiye göre tam/maskeli TC, normal, gece, resmî tatil, fazla, eksik ve izin toplamlarını içerir.
- Personel ana verisi CSV/XLSX, Time Off Used XLSX ve OPEX roster CSV toplu alınır.
- İzin mükerrerliği `Employee ID + tarih` anahtarıyla engellenir.
- 11 saat üstü roster kayıtları bordroya sessizce yazılmaz; ham veri korunarak 7,5 saat simülasyonu audit kaydıyla denenir.
- BY / Regional Executive ve staffing norm eşlemesi değiştirilebilir; warehouse manager ve rider captain norm hesabı dışındadır.
- Türkiye resmî tatilleri 2026-2035 resmî, 2036-2050 doğrulama bekleyen projeksiyon olarak ayrılır.

OPEX Control Center içindeki Workforce modülü aşağıdaki yönetim kapsamını içerir:

- canlı vardiya ve istisna dashboard'u;
- kişisel/depo bazlı puantaj ve CSV export;
- eksik/fazla mesai onay kuyruğu;
- admin veya açıkça yetkilendirilmiş kullanıcıya özel manuel düzeltme;
- düzeltme öncesi/sonrası değerler, gerekçe, kullanıcı ve zaman içeren audit kaydı;
- depo bazlı geofence, GPS sapması ve opsiyonel QR ayar görünümü;
- çalışma/mola kural setleri;
- cihaz eşleştirme ve bütünlük görünümü;
- picker için Vardiyalarım, Arşiv ve Vardiya Detayı mobil ekranları.
- tekli vardiya oluşturma, düzenleme ve toplu CSV vardiya yükleme;
- vardiya yoksa mobil check-in işlemini hem arayüzde hem API'de engelleme;
- seçili kayıtları toplu onaylama;
- depo/geofence ekleme ve düzenleme;
- başlangıç-bitiş saatli tam veya kısmi resmî tatil tanımlama;
- izin türü kuralları ve müdür tarafından izin girişi;
- gece, normal, resmî tatil, eksik, fazla ve izin kırılımlı imzaya uygun puantaj çıktısı.

## Rotalar

- Yönetim paneli: `/workforce`
- Picker deneyimi: `/workforce/app`
- API: `/api/workforce/*`

## Manuel düzeltme güvenliği

Frontend aksiyonu `workforce.manualCorrection` izni olmayan kullanıcıya göstermez. Backend aynı aksiyonu ayrıca kontrol eder. Ham mobil olayın üzerine yazılmaz; düzeltme ayrı audit olayıdır.

Canlı ortamda `X-OPEX-Role` ve `X-OPEX-Permissions` başlıkları doğrudan istemciden kabul edilmemelidir. Bu alanlar SSO/JWT doğrulamasından sonra güvenilir API gateway veya backend middleware tarafından üretilmelidir.

## Windows PowerShell hızlı kurulum

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\INSTALL_OPEX_WORKFORCE_V12_9.ps1
.\START_OPEX_WORKFORCE.ps1
.\TEST_OPEX_WORKFORCE.ps1
```

PowerShell güvenlik nedeniyle mevcut klasördeki bir scripti yalnız adıyla çalıştırmaz. `INSTALL_OPEX_WORKFORCE_V12_9.ps1` yerine başına mutlaka `.\` eklenmelidir.

## Diğer çalıştırma seçenekleri

Frontend:

```bash
npm install
npm run dev
```

Backend:

```bash
python -m pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Test:

```bash
npm run build
python -m unittest backend.app.modules.workforce.test_workforce
```

## Canlıya geçişten önce

## V12.7 mobil self-service ve ürün konfigürasyonu

- Bildirimler tek tek okunabilir/silinebilir; tümünü okundu yap ve tümünü sil aksiyonları vardır.
- Mola başlangıç/bitiş durumu vardiya bazında kalıcıdır; sayfa yenilenince kaybolmaz.
- Picker haftalık izin veya yıllık izin talebi açar; müdür PC/mobil görev kuyruğunda gerekçeli onay veya ret verir.
- Onaylanan izin talebi günlük izin kayıtlarına dönüştürülür, sonuç bildirimi ve audit kaydı üretilir.
- Admin; mola, izin talebi, itiraz, duyuru, bildirim, arşiv, yönetici görevleri ve QR özelliklerini şirket bazında açıp kapatabilir.
- Backend `/leave-requests`, `/feature-flags` ve bildirim okuma/silme uçlarını içerir.

## Canlıya geçişten önce

Yönetim ekranındaki demo/localStorage veri katmanı PostgreSQL veya şirketin tercih ettiği kalıcı veritabanına taşınmalı; SSO/JWT, gerçek depo koordinatları, native mobil konum ve cihaz bütünlük doğrulaması, İK personel ana verisi ve bordro entegrasyonu bağlanmalıdır. API katmanı vardiya, geofence ve cihaz kurallarını ayrıca doğrular; canlıda kimlik başlıkları sadece güvenilir gateway tarafından üretilmelidir.
