const en = {
  title: "Field Mobile Capture",
  subtitle: "Capture assigned Field evidence with a durable offline queue and deterministic replay.",
  back: "Back to Field Intelligence",
  queue: "Offline queue",
  queued: "Queued",
  awaitingAttachment: "Waiting for private attachment upload",
  blocked: "Blocked by evidence policy",
  conflict: "Replay conflict",
  staleAssignment: "Stale assignment",
  retry: "Retry",
  syncNow: "Sync now",
  syncing: "Syncing…",
  queueEmpty: "The offline queue is empty.",
  capturedOffline: "Evidence was added to the encrypted offline queue.",
  capturedOnline: "Evidence was queued and synchronization started.",
  privateUploadUnavailable: "Private evidence upload is not connected. The encrypted attachment remains queued for retry.",
  deviceTrustBoundary: "This browser device ID is a replay identity only. Managed-device trust requires authoritative attestation.",
  cameraTrustBoundary: "The capture attribute is not camera attestation. Camera-only policy requires authoritative capture proof.",
  chooseMission: "Choose mission",
  chooseLocation: "Choose location",
  submit: "Save to offline queue",
  photo: "Capture photo",
  noAssignments: "No active assignments are available in your authorized scope.",
  status: "Status",
  sequence: "Device sequence",
  lastError: "Last result",
  reconnect: "Synchronization resumes when connectivity returns.",
};

const tr = {
  ...en,
  title: "Field Mobil Toplama",
  subtitle: "Atanmış Field kanıtlarını dayanıklı çevrimdışı kuyruk ve deterministik tekrar ile toplayın.",
  back: "Field Intelligence'a dön",
  queue: "Çevrimdışı kuyruk",
  queued: "Kuyrukta",
  awaitingAttachment: "Özel kanıt yüklemesi bekleniyor",
  blocked: "Kanıt politikası engelledi",
  conflict: "Tekrar çakışması",
  staleAssignment: "Eski atama",
  retry: "Tekrar dene",
  syncNow: "Şimdi eşitle",
  syncing: "Eşitleniyor…",
  queueEmpty: "Çevrimdışı kuyruk boş.",
  capturedOffline: "Kanıt şifreli çevrimdışı kuyruğa eklendi.",
  capturedOnline: "Kanıt kuyruğa eklendi ve eşitleme başlatıldı.",
  privateUploadUnavailable: "Özel kanıt yükleme hattı bağlı değil. Şifreli ek dosya tekrar denemek üzere kuyrukta kalır.",
  deviceTrustBoundary: "Bu tarayıcı cihaz kimliği yalnız tekrar kimliğidir. Yönetilen cihaz güveni otoritatif attestation gerektirir.",
  cameraTrustBoundary: "Capture özelliği kamera attestation değildir. Kamera-only politika otoritatif çekim kanıtı gerektirir.",
  chooseMission: "Görev seç",
  chooseLocation: "Lokasyon seç",
  submit: "Çevrimdışı kuyruğa kaydet",
  photo: "Fotoğraf çek",
  noAssignments: "Yetkili kapsamınızda aktif atama yok.",
  status: "Durum",
  sequence: "Cihaz sırası",
  lastError: "Son sonuç",
  reconnect: "Bağlantı geri geldiğinde eşitleme devam eder.",
};

const de = { ...en, title: "Field Mobile Erfassung", queue: "Offline-Warteschlange", syncNow: "Jetzt synchronisieren", retry: "Erneut versuchen" };
const ar = { ...en, title: "التقاط Field للجوال", queue: "قائمة الانتظار دون اتصال", syncNow: "المزامنة الآن", retry: "إعادة المحاولة" };
const fr = { ...en, title: "Capture mobile Field", queue: "File hors ligne", syncNow: "Synchroniser", retry: "Réessayer" };
const es = { ...en, title: "Captura móvil Field", queue: "Cola sin conexión", syncNow: "Sincronizar ahora", retry: "Reintentar" };
const it = { ...en, title: "Acquisizione mobile Field", queue: "Coda offline", syncNow: "Sincronizza ora", retry: "Riprova" };
const nl = { ...en, title: "Field mobiele invoer", queue: "Offlinewachtrij", syncNow: "Nu synchroniseren", retry: "Opnieuw proberen" };
const pl = { ...en, title: "Mobilne zbieranie Field", queue: "Kolejka offline", syncNow: "Synchronizuj", retry: "Ponów" };
const ptBR = { ...en, title: "Captura móvel Field", queue: "Fila offline", syncNow: "Sincronizar agora", retry: "Tentar novamente" };

export const FIELD_MOBILE_MESSAGES = Object.freeze({ tr, en, de, ar, fr, es, it, nl, pl, "pt-BR": ptBR });

export function translateFieldMobile(locale, key) {
  return FIELD_MOBILE_MESSAGES[locale]?.[key] || FIELD_MOBILE_MESSAGES.en[key] || key;
}
