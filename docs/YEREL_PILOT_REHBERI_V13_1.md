# OPEX Workforce V13.1 — kurum API'leri olmadan yerel pilot

Bu mod, kurum OIDC/JWKS, native Apple/Google doğrulama gateway'i, APNs/FCM ve WORM
altyapısı henüz verilmediğinde kapalı bilgisayar/ağ üzerinde süreci denemek içindir.

## Kurulum

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\INSTALL_OPEX_WORKFORCE_LOCAL_PILOT_V13_2.ps1
```

Ardından:

- Yönetim: `http://localhost:8080/workforce`
- Picker: `http://localhost:8080/workforce/app`
- Varsayılan pilot admin: `erdi.aydin@yemeksepeti.com`
- Pilot şifre alanına herhangi bir boş olmayan değer yazılabilir; gerçek parola/SSO değildir.

## Çalışan alanlar

- PostgreSQL üzerinde vardiya, check-in/out kayıt modeli, mola, izin ve görevler
- Puantaj, dönem hesabı, Excel/CSV, dashboard ve depo koordinatları
- Yerel kullanıcı/yetki denemesi ve audit actor kaydı
- Otomatik yerel PostgreSQL dump yedeği

## Bilerek devre dışı olanlar

- Kurumsal SSO/JWT/JWKS ve gerçek parola doğrulaması
- Apple App Attest, Google Play Integrity ve kopyalanamaz tek cihaz kanıtı
- Gerçek GPS/native imza kanıtı ve Dynamic Island
- APNs/FCM dış push bildirimleri
- S3 Object Lock/WORM dış arşivi

Uygulama içi bildirim kayıtları görülebilir; telefon kapalıyken APNs/FCM bildirimi gitmez.
Bu mod internete açılmamalı, gerçek çalışanların TC verisiyle kullanılmamalı ve bordro/mahkeme
delili olarak kabul edilmemelidir.

## Kurum servisleri geldiğinde

`docs/URETIM_YAPILANDIRMA_REHBERI_V13_1.md` adımlarını uygulayın. `.env` içinde
`DOCKOS_ENV=production`, `OPEX_ALLOW_LEGACY_HEADERS=false`,
`VITE_LOCAL_PILOT_MODE=false` ve `OPEX_ATTESTATION_MODE=production` yapın; gerçek OIDC,
gateway, APNs/FCM ve WORM değerlerini girdikten sonra production installer'ı ve kontrolü çalıştırın:

```powershell
.\INSTALL_OPEX_WORKFORCE_V13_1.ps1
.\CHECK_OPEX_CONFIG_V13_1.ps1 -Online
docker compose up -d --build postgres backend notification-worker backup frontend
docker compose --profile worm up -d worm-archiver
```
