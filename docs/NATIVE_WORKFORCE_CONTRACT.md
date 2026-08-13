# OPEX Workforce native uygulama sözleşmesi

## Kimlik ve cihaz kaydı

- Uygulama kurumsal OIDC Authorization Code + PKCE ile oturum açar.
- JWT içinde `sub`, `employee_id`, `roles`, `permissions`, `iat`, `exp` bulunur.
- iOS ilk kayıtta App Attest key/attestation, Android Play Integrity standard token üretir.
- Native uygulama `POST /api/workforce/devices/register` çağrısına cihaz kimliği,
  public key, platform push tokenı ve attestation kanıtını gönderir.
- Sunucu üretimde doğrulama gateway'i yoksa kaydı reddeder. Yalnızca kanıt özeti saklanır.
- Yeni telefon için admin `POST /devices/{person_id}/reset` çağrısı yapar; eski cihaz
  iptal edilir, tek kullanımlık enrollment token üretilir.

## Check-in/out köprüsü

WebView aşağıdaki mesajı gönderir:

```json
{"requestId":"uuid","action":"check-in","shiftId":"SHIFT-...","personId":"12345"}
```

iOS handler adı `opexAttendance`, Android arayüzü
`OpexNative.requestAttendanceProof(json)` olmalıdır. Native katman konum, accuracy,
kayıtlı device id/key id ve tek kullanımlık imzalı challenge üretip şu browser event'ini
çalıştırır:

```javascript
window.dispatchEvent(new CustomEvent("opex-native-attendance-proof", {detail: {
  requestId,
  proof: {latitude, longitude, accuracy_meters, device_id, device_trusted: true,
          device_key_id, challenge_id, signature}
}}));
```

Sunucu vardiya atamasını, tarih penceresini, GPS yarıçapını, accuracy eşiğini,
tek aktif cihazı ve imzayı tekrar doğrular.

## APNs, FCM ve Dynamic Island

- Push token cihaz kaydıyla sunucuya verilir.
- `notification-worker` PostgreSQL outbox'tan `SHIFT_PUBLISHED`,
  `CHECK_IN_REMINDER`, `CHECK_OUT_REMINDER` ve `MANAGER_DECISION` gönderir.
- iOS Live Activity push tokenı `live_activity_token` alanıyla kaydedilir.
- ActivityKit state: `shiftId`, `warehouse`, `breakStartedAt`, `elapsedSeconds`,
  `state` (`working|break|ended`). APNs topic `<bundle>.push-type.liveactivity` olur.
- Dynamic Island/Live Activity yalnız native iOS hedefinde tamamlanır; PWA bildirimi
  yalnızca geliştirme kolaylığıdır ve puantaj kanıtı değildir.
