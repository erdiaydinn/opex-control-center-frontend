# Inventory V20 canlıya geçiş kapısı

V20 kodu, başarısız veya eksik üretim bağımlılıklarını gizlemek yerine sağlık
kontrolünde `degraded` olarak gösterir. Aşağıdaki kapılar kapanmadan dış kullanıcı
trafiğine açılmamalıdır.

| Kapı | Kabul ölçütü |
|---|---|
| Kimlik | OIDC imza, issuer, audience ve süre doğrulaması geçiyor; legacy header kapalı |
| Yetki | COUNTER/WAREHOUSE_MANAGER/INVENTORY_CONTROL/AUDITOR negatif testleri geçiyor |
| Depo kapsamı | JWT `warehouse_scope` başka depoya erişimi 403 ile reddediyor |
| Veri | Üretim PostgreSQL migration ve geri dönüş testi tamam |
| Terminal | Kullanılan her Zebra/Honeywell modelinde EAN-8, EAN-13, GTIN-14, koli ve hızlı tarama kabul testi |
| Offline | Uçak modu, tarayıcı kapanması, tekrar açılış ve aynı olayın iki kez gönderimi testleri |
| Yük | Hedef eşzamanlılıkta p95 API süresi ve hata oranı kabul eşiğinde |
| Audit | Hash zinciri doğrulaması ve Object Lock arşiv denemesi başarılı |
| Yedek | Şifreli yedekten farklı ortama geri dönüş tatbikatı başarılı |
| ERP/WMS | Onaylı belge gönderimi, tekrar deneme, dead-letter ve mutabakat testi |
| Güvenlik | SAST, bağımlılık, container, DAST ve yetki yükseltme testlerinde kritik/yüksek açık yok |
| Operasyon | Pilot depo imzalı UAT ve geri dönüş planı onaylı |

## Puanlama

Kod tamamlanması ile üretim kanıtı aynı şey değildir. Bir kategori ancak kapısı
ölçülmüş ve kanıtlanmışsa 10/10 kabul edilir. V20 paketi bu kanıtları üretmek için
test noktalarını sağlar; cihaz, SSO, ERP ve felaket kurtarma kanıtını kendiliğinden
üretemez.
