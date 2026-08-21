export function normalizeAttendanceProof(proof, now = Date.now()) {
  if (!proof || typeof proof !== "object") throw new Error("Cihaz doğrulama kanıtı alınamadı.");
  const method = proof.local_auth_method;
  if (!["DEVICE_BIOMETRIC", "DEVICE_PASSCODE"].includes(method)) throw new Error("Face ID, biyometri veya cihaz kilidi doğrulaması tamamlanmadı.");
  const authenticatedAt = new Date(proof.local_auth_at).getTime();
  if (!Number.isFinite(authenticatedAt) || Math.abs(now - authenticatedAt) > 120_000) throw new Error("Cihaz doğrulaması eskidi; lütfen yeniden deneyin.");
  if (!proof.device_id || proof.device_trusted !== true) throw new Error("Kayıtlı cihaz kanıtı geçersiz.");
  return { ...proof, local_auth_at: new Date(authenticatedAt).toISOString() };
}
