# OPEX Workforce V13

- Workforce vardiya, puantaj, mola, izin talebi, yönetici görevi, duyuru,
  bildirim, cihaz ve kural kayıtları PostgreSQL JSONB kaynak sistemine taşındı.
- Kurumsal OIDC Authorization Code + PKCE ve backend JWT/JWKS doğrulaması eklendi.
- Picker veri erişimi JWT `employee_id` ile kendi kayıtlarıyla sınırlandı.
- TC AES-256-GCM ile şifreleniyor; yetkisiz kullanıcıya maskeli dönüyor.
- 127 depo koordinatı kurumsal CSV'den normalize edildi ve Türkiye sınırlarında doğrulandı.
- App Attest / Play Integrity fail-closed doğrulama adaptörü ve tek cihaz kaydı eklendi.
- APNs/FCM zamanlanmış notification outbox ve ayrı worker eklendi.
- Native check-in/out ve ActivityKit/Dynamic Island entegrasyon sözleşmesi tanımlandı.
- Otomatik pg_dump + checksum, S3 Object Lock WORM audit, restore runbook,
  Sentry, Prometheus/Grafana ve dönen container logları eklendi.
- PowerShell kurulum: `.\INSTALL_OPEX_WORKFORCE_V13.ps1`.

Üretim anahtarları pakete gömülü değildir. OIDC, App Attest/Play Integrity,
APNs, FCM, S3/WORM ve Sentry değerleri `.env`/secret manager üzerinden verilmelidir.

## V13.1 düzeltmesi

- Windows PowerShell 5.1 / eski .NET için desteklenmeyen statik
  `RandomNumberGenerator.Fill()` çağrısı kaldırıldı; `Create().GetBytes()` kullanıldı.
- OIDC/JWKS, native attestation gateway, APNs, FCM ve S3 Object Lock/WORM için ayrıntılı
  Türkçe kurulum rehberi ile gizli değerleri göstermeyen yapılandırma kontrol scripti eklendi.
- Kurum servisleri henüz hazır değilken PostgreSQL ve iş akışlarını kapalı bilgisayarda
  denemek için ayrı, açıkça işaretli Yerel Pilot kurulumu eklendi. Bu mod production
  güvenliği veya dış push/WORM varmış gibi davranmaz.

## V13.2 test hazırlık paketi

- Yerel pilot picker kimliği production frontend derlemesinde de `100184` test personeline
  bağlandı; boş Employee ID nedeniyle mobil bootstrap'ın çalışmaması giderildi.
- Native uygulama olmadan fonksiyon testi için yalnız Yerel Pilot modunda atanmış depo
  koordinatı ve kayıtlı seed cihaz kullanılır; her işlem audit'te `pilot_simulation=true`
  olarak açıkça işaretlenir. Production modunda bu yol derlemeye kapalıdır.
- Otomatik Docker/PostgreSQL/API/frontend kontrolü, test öncesi dump+SHA256 yedeği,
  LAN telefon adresi, kabul listesi ve hassas dosyaları dışlayan teşhis paketi eklendi.

### V13.2.1 Windows ZIP düzeltmesi

- Bazı Windows ZIP çıkarıcılarının başında nokta bulunan `.env.example` dosyasını atlaması
  nedeniyle görünür `ENV_TEMPLATE_V13_2.txt` yedeği eklendi. Tüm V13 kurucuları önce
  `.env.example`, bulunamazsa görünür şablonu kullanır.
