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
          device_key_id, challenge_id, signature,
          local_auth_method: "DEVICE_BIOMETRIC", local_auth_at}
}}));
```

Native katman bu kanıtı üretmeden hemen önce LocalAuthentication (iOS) veya
BiometricPrompt (Android) ile kullanıcı varlığını doğrular. Face ID/yüz görüntüsü,
parmak izi ya da biyometrik şablon uygulamaya ve sunucuya aktarılmaz. Sunucu yalnız
`DEVICE_BIOMETRIC`/`DEVICE_PASSCODE` sonucunu, zamanını ve tek kullanımlık cihaz
imzasını kabul eder; doğrulama 120 saniye içinde kullanılmazsa reddedilir.

Sunucu vardiya atamasını, tarih penceresini, GPS yarıçapını, accuracy eşiğini,
tek aktif cihazı ve imzayı tekrar doğrular.

Challenge akışı:

1. Native katman kayıtlı `device_id` ile `POST /api/workforce/devices/challenge`
   çağrısını yapar.
2. Dönen `challenge` cihazın attested private key'iyle imzalanır; private key
   Secure Enclave/Android Keystore dışına çıkmaz.
3. `challenge_id` ve base64url `signature` check-in/out kanıtına eklenir.
4. Challenge iki dakika geçerlidir ve başarılı GPS + imza doğrulamasından sonra
   tek kullanımlık olarak tüketilir; replay reddedilir.

Konum yalnızca kullanıcının başlattığı check-in ve check-out işlemlerinde tek nokta
kanıtı olarak alınır. Vardiya içinde veya dışında arka planda sürekli rota/konum
izleme Workforce sözleşmesinin parçası değildir ve sunucuda saklanmaz.

## APNs, FCM ve Dynamic Island

- Push token cihaz kaydıyla sunucuya verilir.
- `notification-worker` PostgreSQL outbox'tan `SHIFT_PUBLISHED`,
  `CHECK_IN_REMINDER`, `CHECK_OUT_REMINDER` ve `MANAGER_DECISION` gönderir.
- iOS Live Activity push tokenı `live_activity_token` alanıyla kaydedilir.
- ActivityKit state: `shiftId`, `warehouse`, `breakStartedAt`, `elapsedSeconds`,
  `state` (`working|break|ended`). APNs topic `<bundle>.push-type.liveactivity` olur.
- Dynamic Island/Live Activity yalnız native iOS hedefinde tamamlanır; PWA bildirimi
  yalnızca geliştirme kolaylığıdır ve puantaj kanıtı değildir.
