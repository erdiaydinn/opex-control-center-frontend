import assert from "node:assert/strict";
import { normalizeAttendanceProof } from "../src/modules/workforce/workforceAttendanceProof.js";

const now = Date.parse("2026-08-13T10:00:00.000Z");
const proof = normalizeAttendanceProof({
  device_id: "DEVICE-1",
  device_trusted: true,
  local_auth_method: "DEVICE_BIOMETRIC",
  local_auth_at: "2026-08-13T09:59:30.000Z",
  latitude: 41.0572,
  longitude: 28.9973,
  accuracy_meters: 5,
}, now);

assert.equal(proof.local_auth_method, "DEVICE_BIOMETRIC");
assert.equal(proof.local_auth_at, "2026-08-13T09:59:30.000Z");
assert.throws(() => normalizeAttendanceProof({ ...proof, local_auth_method: "NONE" }, now), /doğrulaması tamamlanmadı/);
assert.throws(() => normalizeAttendanceProof({ ...proof, local_auth_at: "2026-08-13T09:56:00.000Z" }, now), /doğrulaması eskidi/);
assert.throws(() => normalizeAttendanceProof({ ...proof, device_trusted: false }, now), /Kayıtlı cihaz kanıtı geçersiz/);

console.log("Workforce attendance proof tests passed.");
