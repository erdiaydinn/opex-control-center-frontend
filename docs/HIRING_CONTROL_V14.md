# OPEX Hiring Control V14

Hiring Control, depo bazlı kadro normunu canlı çalışan ana verisi ve açık işe
alım talepleriyle birleştirir. Mağaza müdürleri genel kadro normundan ayrıdır;
varsayılan müdür kapasitesi bir, Fulya için iki kişidir.

## Karar hesabı

`kullanılabilir = kapasite - (aktif + açık talep - doğrulanmış planlı ayrılış)`

- Mağaza Görevlisi, Mağaza Müdür Yardımcısı ve Mağaza Destek Görevlisi kadro
  normuna dahildir.
- Mağaza Müdürü ayrı kapasite kuralıyla değerlendirilir.
- Aynı depo/pozisyondaki bekleyen, onaylı veya sourcing durumundaki talepler
  yeniden boş kadro olarak gösterilmez.
- Planlı ayrılış yalnızca aynı depodaki aktif çalışan doğrulanırsa kredi üretir.
- Planlı ayrılış talebi istifa belgesi yüklenmeden onaya açılamaz.

## Onay ve bildirim

Onayda karar hesabı güncel veriyle tekrar çalıştırılır. İK ve third-party alıcı
grupları için ayrı outbox kaydı açılır. SMTP hazırsa e-posta gönderilir; hazır
değilse kayıt hata bilgisiyle kalır ve ekrandan yeniden denenebilir.

SMTP sırları arayüzde tutulmaz. `.env` içinde `RECRUITMENT_SMTP_*` alanlarıyla
sunucu tarafında yapılandırılır.

## Yetkiler

- Depo/Bölge yöneticisi: görüntüleme ve talep oluşturma
- İK: görüntüleme, karar, belge, norm, alıcı ve teslim kuyruğu yönetimi
- Admin/Super Admin: tüm işlemler

## Audit

Talep oluşturma, istifa belgesi yükleme (SHA-256), karar, norm değişikliği,
alıcı ayarı ve e-posta denemeleri mevcut hash-zincirli Workforce audit kaydına
eklenir.
