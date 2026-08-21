# Workforce V30 field acceptance matrix

Bu matris PR #55 → #58 → #61 hattında `field-production-ready >=95%` kararının kanıt kapısıdır. Otomatik fixture veya mock sonucu gerçek cihaz, gerçek IdP, müşteri dosyası ya da fiziksel saha kanıtı yerine geçmez.

CI kanıt dosyaları yalnız runner'ın geçici `RECRUITMENT_EVIDENCE_DIR` alanında üretilir; kalıcı müşteri kanıt deposu ve retention policy staging/pilot kabulünde ayrıca doğrulanır.

| Acceptance senaryosu | Otomatik kanıt | Dış kanıt / geçiş koşulu | Durum |
|---|---|---|---|
| Vardiyasız check-in, duplicate istek | Backend/API testleri | Pilot cihaz tekrar denemesi | Otomatik geçti; saha bekliyor |
| Check-in/out, mola, net süre | Backend/API testleri | Fiziksel cihaz + vardiya | Otomatik geçti; saha bekliyor |
| Gece vardiyası, >11 saat, izin, resmi tatil | Backend/API testleri | Onaylı pilot bordro örneği | Otomatik geçti; müşteri kabulü bekliyor |
| TC → Employee ID → Roster ID | Import/identity testleri | Gerçek müşteri HR/roster dosyası | Fixture geçti; müşteri dosyası bekliyor |
| Toplu personel/izin/puantaj | Frontend + backend import testleri | Anonimleştirilmiş gerçek format | Fixture geçti; müşteri dosyası bekliyor |
| Employee exit/resignation | Device/challenge/shift erişim kapatma testi | Kurumsal IdP session revoke kanıtı | Uygulama kapatması geçti; IdP bekliyor |
| Tek cihaz, replacement/lost device | Lifecycle API testleri | Fiziksel iOS + Android | Simülasyon geçti; cihaz bekliyor |
| Face ID/biometric user presence | Contract testleri; template/görüntü saklanmaz | Fiziksel cihaz Secure Enclave/Keystore kanıtı | Cihaz bekliyor |
| App Attest / Play Integrity | Adaptör ve hata testleri | Apple/Google production credential + gerçek verdict | Dış credential bekliyor |
| GPS/geofence/spoof/failure | Koordinat/accuracy testleri | Depo boundary walk, weak signal, multipath | Saha bekliyor |
| Offline/network interruption/stale token | API hata ve auth testleri | Fiziksel cihaz uçak modu + gerçek IdP token | Dış kabul bekliyor |
| Concurrent manager edits | PostgreSQL CAS/stale-write testi | Staging çoklu instance soak | CI kanıtı var; staging soak bekliyor |
| PostgreSQL V29→V30 migration | CI seeded upgrade rehearsal | Production snapshot clone rehearsal | CI kanıtı var; staging clone bekliyor |
| Database restart, backup/restore | CI `pg_dump` + izole `pg_restore` doğrulaması | Staging restart/RPO-RTO ölçümü | CI kanıtı var; staging DR bekliyor |
| Pilot load/concurrency | 500 işlem/24 worker PostgreSQL CI gate | Staging pilot-shape load ve soak | CI gate var; staging bekliyor |
| Notification retry/idempotency | Transactional outbox, deterministic Message-ID, retry/dead-letter | Gerçek SMTP/push provider retry | Kod kanıtı var; provider bekliyor |
| Tenant/store/role isolation | PostgreSQL RLS + production JWT scope API testleri | Kurumsal tenant claim testi | Otomatik geçti; gerçek SSO bekliyor |
| Norm→Vacancy→Candidate→Evidence→Decision→Hire→Employee Master→ilk vardiya | PostgreSQL transaction/integration testi | HR pilot acceptance | CI koşacak; HR kabulü bekliyor |
| Evidence access/retention/audit | HR permission, retention metadata, atomik karar audit’i | DPO retention policy onayı | Kod kanıtı var; politika onayı bekliyor |
| Native signed build/internal distribution | Yok | App Store Connect/TestFlight + Play Internal SHA/artifact | Bloker |

## %95 kuralı

Gerçek kurumsal SSO, gerçek iOS/Android cihaz, gerçek müşteri HR girdisi, staging load/DR ve pilot acceptance kanıtlarının tümü bağlanmadan bu çalışma `%95 field-production-ready` olarak raporlanamaz.
