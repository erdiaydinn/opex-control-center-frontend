# OPEX Workforce V13.1 üretim yapılandırma rehberi

Bu rehber Windows PowerShell, Docker Desktop ve proje kökündeki `.env` dosyası içindir.
Gizli anahtarları e-posta, Teams/Slack mesajı veya kaynak koda koymayın. `.env`, `.p8`
ve Google servis hesabı JSON'u Git'e eklenmemelidir.

## 1. Güvenli başlangıç sırası

PowerShell'i ZIP'i çıkardığınız klasörde açın:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\INSTALL_OPEX_WORKFORCE_V13_1.ps1
notepad .env
```

Kurucu `.env` yoksa güçlü PostgreSQL, gateway, PII ve Grafana anahtarlarını üretir.
Kurulumun ilk çalışmasında örnek OIDC adresleri için uyarı görülmesi normaldir. Aşağıdaki
kurum değerlerini tamamlamadan sistemi gerçek personele açmayın.

Değerleri kaydettikten sonra:

```powershell
.\CHECK_OPEX_CONFIG_V13_1.ps1 -Online
docker compose up -d --build postgres backend notification-worker backup frontend
docker compose --profile worm up -d worm-archiver
docker compose --profile observability up -d prometheus grafana
docker compose ps
```

OIDC'ye ait `VITE_...` değerleri frontend derleme zamanında alındığı için `.env`
değişikliğinden sonra `--build frontend` zorunludur. Backend/push/WORM değişikliklerinde
ilgili container'ı yeniden oluşturmak gerekir.

### Workforce V29 PostgreSQL migration kapısı

Production backend kendi kendine DDL çalıştırmaz. Uygulamayı başlatmadan önce migration
rolüyle `backend/migrations/002_workforce_v29.sql` uygulanmalıdır. Runtime rolünün tablo
sahibi veya migration rolü olması gerekmez.

```dotenv
DATABASE_URL=postgresql://opex_runtime:...@postgres:5432/opex
WORKFORCE_TENANT_ID=eay-tr
WORKFORCE_AUTO_MIGRATE=false
```

Migration; tenant bazlı row-level security, koleksiyon revision kaydı, atomik state+audit
commit'i ve tenant-scoped notification outbox oluşturur. `WORKFORCE_TENANT_ID` production'da
zorunludur. `/api/workforce/health` içinde `schema_version=29`,
`atomic_snapshot_audit=true` ve `postgresql=true` görülmeden gerçek personele trafik açmayın.

Runtime PostgreSQL rolü süper kullanıcı veya tablo sahibi olmamalıdır. Migration rolü bir kez
`workforce_tenant_bindings` tablosuna runtime rolü ile tenant kimliğini bağlamalı ve runtime
rolüne yalnız entity/version/outbox DML, audit için SELECT+INSERT, migration tablosu için SELECT
ve gerekli sequence kullanım haklarını vermelidir. RLS tenant seçimini istemcinin değiştirebildiği
bir session değişkeninden değil bu role→tenant bağından yapar. Aynı runtime rolünü birden fazla
tenant için kullanmayın.

## 2. Kurumsal OIDC, JWT ve JWKS

Kurumun IAM/SSO ekibinden OPEX için **public client + Authorization Code + PKCE** kaydı
açmasını isteyin. Client secret web tarayıcısına konulmamalıdır. İzin verilen redirect URI,
üretim alan adınızla birebir aynı olmalıdır; örneğin
`https://opex.sirketiniz.com/auth/callback`.

Kimlik sağlayıcının issuer adresinde şu belge açılmalıdır:

```text
https://SSO-ISSUER/.well-known/openid-configuration
```

Bu JSON'daki alanları şöyle eşleyin:

| `.env` alanı | Kaynak |
|---|---|
| `OPEX_OIDC_ISSUER` | Discovery belgesindeki `issuer` |
| `OPEX_OIDC_JWKS_URL` | `jwks_uri` |
| `VITE_OIDC_AUTHORIZE_URL` | `authorization_endpoint` |
| `VITE_OIDC_TOKEN_URL` | `token_endpoint` |
| `VITE_OIDC_CLIENT_ID` | IAM ekibinin açtığı OPEX web client ID |
| `OPEX_OIDC_AUDIENCE` | API'nin resource/audience kimliği |
| `VITE_OIDC_REDIRECT_URI` | IAM'de izin verilen kesin callback URL |

JWT içinde en az `sub`, `employee_id`, `roles`, `permissions`, `iat` ve `exp` olmalıdır.
Depo/bölge yöneticilerinde ayrıca yetkili canonical depo ID'lerini içeren
`warehouse_scope` claim'i zorunludur; claim eksikse Workforce production istekleri reddedilir.
Kurum farklı claim adı kullanıyorsa `OPEX_OIDC_ROLES_CLAIM` ve
`OPEX_OIDC_PERMISSIONS_CLAIM`, `OPEX_OIDC_EMPLOYEE_ID_CLAIM` ve
`OPEX_OIDC_WAREHOUSE_SCOPE_CLAIM` değerlerini değiştirin. `OPEX_ALLOW_LEGACY_HEADERS=false`
olarak kalmalıdır.

Örnek (gerçek değer değildir):

```dotenv
OPEX_OIDC_ISSUER=https://login.sirketiniz.com/realms/opex
OPEX_OIDC_AUDIENCE=opex-workforce-api
OPEX_OIDC_JWKS_URL=https://login.sirketiniz.com/realms/opex/protocol/openid-connect/certs
VITE_OIDC_CLIENT_ID=opex-control-center-web
VITE_OIDC_AUTHORIZE_URL=https://login.sirketiniz.com/realms/opex/protocol/openid-connect/auth
VITE_OIDC_TOKEN_URL=https://login.sirketiniz.com/realms/opex/protocol/openid-connect/token
VITE_OIDC_REDIRECT_URI=https://opex.sirketiniz.com/auth/callback
```

## 3. Apple App Attest ve Google Play Integrity

Bu iki satıra Apple/Google anahtarı yazılmaz. V13.1 backend'i native uygulamanın ürettiği
kanıtı doğrulayan kurum içi HTTPS gateway'ini çağırır:

```dotenv
OPEX_ATTESTATION_MODE=production
APPLE_APP_ATTEST_VERIFY_URL=https://device-trust.sirketiniz.com/apple/verify
GOOGLE_PLAY_INTEGRITY_VERIFY_URL=https://device-trust.sirketiniz.com/google/verify
OPEX_ATTESTATION_GATEWAY_TOKEN=UZUN_RASTGELE_KURUM_ICI_TOKEN
```

Native ekip iOS'ta App Attest anahtarı/attestation/assertion üretmeli; gateway Apple kök
sertifika zincirini, nonce/challenge'i, App ID'yi, imza sayacını ve istek bağını doğrulamalıdır.
Android uygulama Standard Play Integrity tokenı üretmeli; gateway tokenı Google Play
sunucusunda çözüp paket adı, sertifika özeti, app/device/account verdict'leri, zaman ve
`requestHash` bağını doğrulamalıdır. Başarılı kanıt tek cihaz kaydıyla eşleştirilir.

Gateway henüz yoksa yalnız kapalı yerel geliştirmede
`OPEX_ATTESTATION_MODE=development` kullanılabilir. Bu değerle üretim check-in/out açmayın.

## 4. APNs (iPhone bildirimleri)

1. Apple Developer hesabında OPEX native uygulamasının Bundle ID'sini açın ve Push
   Notifications yeteneğini etkinleştirin.
2. **Certificates, Identifiers & Profiles > Keys** alanında APNs yetkili bir anahtar
   oluşturun ve `.p8` dosyasını indirin. Apple bu dosyanın tekrar indirilmesine izin
   vermeyebilir; kurumsal secret manager'da yedekleyin.
3. ZIP klasöründe `secrets` altına kopyalayın:

```powershell
Copy-Item "$HOME\Downloads\AuthKey_ABC123DEFG.p8" ".\secrets\AuthKey_ABC123DEFG.p8"
```

4. `.env`:

```dotenv
APNS_TEAM_ID=APPLE_TEAM_ID
APNS_KEY_ID=ABC123DEFG
APNS_BUNDLE_ID=com.sirketiniz.opexworkforce
APNS_ENV=production
APNS_PRIVATE_KEY_HOST_PATH=./secrets/AuthKey_ABC123DEFG.p8
```

TestFlight/App Store için `production`, yalnız development provisioning ile cihaz testi
için `sandbox` kullanın. Native uygulama APNs device tokenını cihaz kayıt API'sine vermelidir.

## 5. FCM (Android bildirimleri)

1. Firebase/Google Cloud'da Android uygulamasının projesini açın ve Cloud Messaging API'yi
   etkinleştirin.
2. Yalnız mesaj göndermek için gerekli en dar yetkili servis hesabı oluşturun. Üretimde
   Workload Identity/IAM tercih edilir; bu Docker paketi yerel kurulumda servis hesabı
   JSON'u da destekler.
3. JSON'u `secrets` altına kopyalayın:

```powershell
Copy-Item "$HOME\Downloads\opex-fcm-service-account.json" ".\secrets\google-service-account.json"
```

4. `.env`:

```dotenv
FCM_PROJECT_ID=firebase-project-id
GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH=./secrets/google-service-account.json
```

Native Android uygulama FCM registration tokenını cihaz kayıt API'sine göndermelidir.

## 6. S3 Object Lock / WORM audit arşivi

1. Ayrı bir AWS hesabında veya güvenlik hesabında versioning ve **Object Lock** açık bir
   S3 bucket hazırlayın.
2. Retention modunu `COMPLIANCE`, süreyi kurum hukuk/İK politikasına göre belirleyin.
   Varsayılan paket değeri 3650 gündür (10 yıl); bu hukuki karar yerine geçmez.
3. Uygulama kimliğine yalnız gerekli bucket üzerinde `s3:PutObject` ve doğrulama için sınırlı
   listeleme/okuma yetkisi verin. Üretimde IAM role tercih edin.
4. `.env`:

```dotenv
WORKFORCE_WORM_BUCKET=opex-workforce-audit-prod
WORKFORCE_WORM_RETENTION_DAYS=3650
WORM_INTERVAL_SECONDS=86400
WORKFORCE_WORM_SSE=AES256
S3_ENDPOINT_URL=
AWS_DEFAULT_REGION=eu-central-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
```

AWS üzerinde IAM role kullanıyorsanız anahtar satırları boş kalır. Windows'taki yerel Docker
role alamıyorsa sadece bu kurulum için ayrılmış erişim anahtarlarını girin. MinIO veya başka
S3 uyumlu servis kullanıyorsanız `S3_ENDPOINT_URL=https://...` yazın ve Object Lock
uyumluluğunu ayrıca kanıtlayın.

WORM servisini başlatın ve logu kontrol edin:

```powershell
docker compose --profile worm up -d worm-archiver
docker compose logs --tail 100 worm-archiver
```

Başarılı arşivleme tek başına yeterli değildir: bucket'taki nesnenin `COMPLIANCE` retention
tarihini, hash-chain sürekliliğini ve farklı hesapta silinemediğini test edin.

## 7. Kontrol ve değişiklik sonrası yeniden başlatma

```powershell
.\CHECK_OPEX_CONFIG_V13_1.ps1 -Online
docker compose config --quiet
docker compose up -d --build backend notification-worker frontend
docker compose --profile worm up -d worm-archiver
docker compose ps
docker compose logs --tail 100 backend notification-worker worm-archiver
```

Son kabul testinde gerçek iPhone ve Android cihazla OIDC oturumu, cihaz kaydı, depo içi/dışı
check-in, cihaz sıfırlama, vardiya yayını, check-in/out hatırlatması, yönetici kararı, WORM
nesnesi ve PostgreSQL restore tatbikatı ayrı ayrı doğrulanmalıdır.
