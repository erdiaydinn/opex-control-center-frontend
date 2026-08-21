# V13 production geçiş kapıları

- [ ] Kurumsal OIDC issuer, JWKS, audience ve web client kaydı tamamlandı.
- [ ] JWT rolleri/izinleri ve `employee_id` claim'i doğrulandı.
- [ ] `OPEX_PII_KEY` secret manager'a alındı; düz metin TC loglanmadığı test edildi.
- [ ] Apple App Attest ve Google Play Integrity doğrulama gateway'leri canlı.
- [ ] APNs `.p8`, team/key/bundle id ve FCM service account tanımlı.
- [ ] 127 depo koordinatı saha örnekleriyle onaylandı; radius/accuracy depo bazında düzenlendi.
- [ ] PostgreSQL yedek restore tatbikatı geçti; WORM bucket Object Lock açık.
- [ ] Sentry PII kapalı, Prometheus alarm alıcıları ve log retention politikası tanımlı.
- [ ] Native iOS/Android güvenlik testi, root/jailbreak politikası ve pentest tamamlandı.
- [ ] İK/bordro dönem kapanışı ve audit delil çıktısı kullanıcı kabul testini geçti.
