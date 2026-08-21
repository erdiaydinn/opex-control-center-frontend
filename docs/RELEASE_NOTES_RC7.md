# DockOS RC7 Internal Test

## RC7.5 arayüz düzeni ve profesyonel form deneyimi

- Toplu PO yükleme akışı; numaralı adım kartları, açıklamalar, geniş dosya bırakma alanı ve ayrı işlem çubuğuyla yeniden tasarlandı.
- Dosya adı ve doğrulama sonucu artık belirgin durum etiketleriyle gösterilir; yükleme aksiyonu içerikten ayrıldı.
- Tedarikçi e-posta erişimi; kullanıcı kimliği, erişim durumu, tedarikçi kapsamı ve depo kapsamı olarak görsel bölümlere ayrıldı.
- E-posta ve dil alanları standart 48 piksel kontrol yüksekliğine taşındı; aktif/pasif erişim ayrı bir durum kartı oldu.
- Dar ekranlarda form kolonları ve işlem butonları tek kolona iner; açık/koyu tema renkleri ortak tokenları kullanır.
- Yeni açıklamaların Türkçe, İngilizce, Almanca ve Arapça çevirileri tamamlandı.

## RC7.4 tek randevu bloğu ve çakışma temizliği

- `10:00 - 14:00` gibi çok saatli bir blok açıldığında aynı aralıktaki saatlik slotlar otomatik kaldırılır.
- Tedarikçi portalında blok başına yalnızca tek randevu seçeneği gösterilir; kapasite tüm bloğa aittir.
- Mevcut RC7.3 state içindeki çok saatli blok + saatlik slot tekrarları backend başlangıcında otomatik temizlenir.
- Çakışan saatlik slotta aktif rezervasyon varsa yeni blok güvenli şekilde reddedilir.
- Slot düzenleme sırasında oluşabilecek yeni zaman çakışmaları da aynı kuralla yönetilir.

## RC7.3 yönetilebilir slot planı

- Tarih seçiminden sonra `Tam Günü Blokla` veya `Parçalı / Saatlik Yönet` seçimi eklendi.
- Tam gün bloklanan tarihlerde, ihtiyaç halinde belirli saatler yeniden açılabilir.
- Slot yönetim tablosunda saat başlangıcı/bitişi, palet ve SKU kapasitesi düzenlenebilir.
- Aktif rezervasyonlu slotların saat değişikliği ve silinmesi güvenli şekilde engellenir.
- Silinen slotlar kalıcı silme kaydına alınır; backend yeniden başladığında otomatik oluşmaz.
- Kapalı slotlar varsayılan olarak gizlenir ve istenirse ayrı seçenekle görüntülenir.
- Yeni akışın TR/EN/DE/AR çevirileri ve backend testleri eklendi.

## RC7.2 genişletilebilir saat blokları

- Kapasite ekranına başlangıç saati, blok süresi ve blok adedi ile yeni slot üretme alanı eklendi.
- Akşam/gece slotları ve `23:30 - 00:30` gibi gece yarısını geçen bloklar desteklenir.
- Yeni bloklar mevcut seçime eklenir; daha sonra yeni bloklar ilave edilerek günlük slot sayısı artırılabilir.
- Slot formatı backend tarafında doğrulanır ve oluşturulan slotlar seçili tarihler için kalıcı kapasite kaydı olur.
- Yeni alanların Türkçe, İngilizce, Almanca ve Arapça çevirileri eklendi.

## RC7.1 installer düzeltmesi

- Installer içindeki `GO_LIVE_CHECKLIST_RC6.md` adı `GO_LIVE_CHECKLIST_RC7.md` olarak düzeltildi.
- Ops yardımcı dokümanları eksik olsa bile ana kod kurulumu artık durmaz; uyarı vererek devam eder.

## Koyu tema

- Tablo başlıklarının beyaz zemin/beyaz yazı sorunu giderildi.
- Merkez depo sayfasının sabit açık arka planı tema değişkenine bağlandı.
- Tarih çipleri, saat butonları, tamamla/revizyon/düzenle/iptal aksiyonları tema tokenlarına taşındı.
- PO, bildirim ve KPI tablolarının başlık kontrastı ortak koyu tema kuralıyla düzeltildi.

## E-posta erişim eşleştirmesi

- Admin menüsüne `Erişim Yönetimi` eklendi.
- E-posta → bir veya daha fazla tedarikçi → tüm veya seçili merkez depolar eşleştirmesi eklendi.
- Aktif/pasif erişim ve tercih edilen dil kaydedilir.
- Eşleşmeler kalıcı state ve audit log içinde tutulur.
- Yetki yalnızca frontend filtresi değildir; PO, slot, rezervasyon oluşturma/görüntüleme ve iptal API'lerinde uygulanır.
- Canlı yayın readiness kapısına aktif tedarikçi erişim eşleşmesi kontrolü eklendi.

## İç test/GitHub hazırlığı

- GitHub Actions doğrulaması eklendi.
- Backend testleri, frontend bundle ve dört dil çeviri kapsam kontrolü CI içinde çalışır.
- `.gitignore` state, secret, env, build ve zip dosyalarını dışlar.
- RC7 tek-worker iç pilot test sürümüdür.
