# Workforce Field Pilot V28

Bu sürüm `product/workforce-experience-v27` üzerine eklenen saha-pilot acceptance
katmanıdır. PR #55 ve PR #58'deki canonical Workforce davranışlarını korur.

## Acceptance kapsamı

| Alan | Sunucu davranışı | Test kanıtı |
|---|---|---|
| Vardiya zorunluluğu | Atanmış vardiya yoksa check-in reddedilir | `test_check_in_requires_assigned_shift` |
| Check-in/out | Açık kayıt tekilleştirilir; check-out brüt−mola net süreyi hesaplar | canlı checkout ve gece testleri |
| Kimlik zinciri | TC özeti → Employee ID → Roster ID alias çözümlemesi sunucuda yapılır | resolver ve import testleri |
| Toplu import | Personel, izin, işe giriş/çıkış ve puantaj eşleşmeyenleri raporlar | import testleri |
| 11 saat | Planlama sert blok; fiili/import kayıt yönetici istisnası | canlı ve import exception testleri |
| Gece vardiyası | Gün aşımı ve 20:00–06:00 gece dakikası hesaplanır | overnight testi |
| İzin/tatil | Onaylı izin vardiya/check-in'i engeller; import edilen resmi tatil etiketlenir | leave/holiday testi |
| Tek cihaz | Reset + 15 dakika enrollment + attestation + tek aktif cihaz | cihaz lifecycle kodu |
| Cihaz challenge | 2 dakika, kullanıcı/cihaz bağı, ECDSA/RSA/Ed25519 imza ve replay engeli | signed challenge testi |
| GPS/geofence | Accuracy ve depo yarıçapı sunucuda doğrulanır | GPS testleri |
| Local user presence | Production'da cihaz biyometrisi veya cihaz parolası sonucu zorunlu | local-auth testleri |
| Production SSO | İmzalı OIDC JWT ve yapılandırılabilir Employee ID claim'i | security testleri |
| Depo yetki kapsamı | Yönetici read/write işlemleri JWT `warehouse_scope` ile filtrelenir; eksik claim production'da fail-closed | manager scope API acceptance testi |
| Recruitment activation | Employee Master → Norm → Vacancy → Approval → Hire → Workforce active | recruitment activation testleri |
| PostgreSQL doğruluğu | Tenant RLS + atomik state/audit + optimistic revision; stale write fail-closed | gerçek PostgreSQL acceptance job |
| Restart dayanımı | Enrollment ve tek kullanımlık cihaz challenge durumları snapshot içinde kalıcıdır | process-state reload testi |

## Veri minimizasyonu

- Biyometrik görüntü veya şablon alınmaz ve saklanmaz.
- Private device key cihaz Secure Enclave/Keystore dışına çıkmaz.
- Konum yalnız kullanıcının başlattığı check-in/out anında tek nokta kanıtıdır.
- Sürekli veya vardiya dışı rota/konum izleme yoktur.
- TC açık değeri import/audit sonuçlarına yazılmaz; eşleşme SHA-256 özetiyle yapılır,
  saklama AES-256-GCM korumalıdır.

## Production pilot kapıları

Pilot açılmadan önce `/api/workforce/health` içindeki production kontrolleri yeşil
olmalıdır: Workforce V29 PostgreSQL migration/tenant kimliği, OIDC issuer/audience,
Employee ID ve `warehouse_scope` claim eşlemesi, `OPEX_PII_KEY`, Apple App Attest gateway, Google Play Integrity gateway ve local user-presence zorunluluğu. Ayrıca gerçek iOS/Android
buildleri, kurumsal IdP claim eşlemesi, depo koordinat onayı ve pilot import örnekleriyle
cihaz üstü UAT tamamlanmalıdır.

Avans, harcama, seyahat, yan hak ve Budget Intelligence bu sürümün kapsamı dışındadır.
