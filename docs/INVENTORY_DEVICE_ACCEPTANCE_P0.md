# EAY Inventory P0 — Zebra Device Acceptance Matrix

This matrix is evidence-driven. A row remains `BLOCKED` until a signed release
APK is deployed by the corporate MDM to the physical device and the evidence
bundle contains model, Android/MX/DataWedge versions, APK SHA-256, tester,
timestamp, test result and exported device diagnostics.

| Model family | Minimum coverage | Scanner / barcode cases | Performance / endurance | Current status |
|---|---|---|---|---|
| TC21 / TC26 | Android 11 and latest supported LifeGuard | EAN-8/13, GS1-128, GS1 DataMatrix, QR, Code 128; damaged, glossy, low contrast, duplicate burst | 10k scans; p95 scan-to-local-commit <150 ms; 8h queue; 20%→5% battery run | BLOCKED — physical device required |
| TC52 / TC57 | Android 11/13 and current MX/DataWedge | same suite; SE4710 near/far and rapid consecutive scans | 10k scans, Wi-Fi roam, airplane-mode cycle, process kill/restart | BLOCKED — physical device required |
| TC53 / TC58 | Android 13/14 and 16 KB-compatible release | same suite; GS1 lot/serial/expiry edge cases | 20k scans; network flapping; thermal/battery observation | BLOCKED — physical device required |
| MC33xx | keypad and touch variants | trigger/key mapping, long Code 128, pallet/location codes | 8h shift, suspend/resume, charger removal | BLOCKED — physical device required |
| MC94xx | Android 13+ and current LifeGuard | long-range scan, dense barcode field, damaged labels | 20k scans, warehouse roam, cold/reconnect behavior | BLOCKED — physical device required |

## Mandatory scenario set

1. MDM force-install, managed UUID injection and one-time enrollment consumption.
2. Company OIDC authorization-code + PKCE; expiry while offline; refresh/re-auth.
3. DataWedge profile creation and MX API allowlisting; delivery only to the exact
   production package/signing certificate.
4. Blind count: terminal receives task/location metadata but never expected
   quantity, cost, variance or the expected SKU universe.
5. Expected and unexpected SKU; malformed/oversized/Unicode barcode; duplicate
   decoder burst; same barcode in different symbologies.
6. Offline for 8 hours, process death, device reboot and encrypted Room reopen.
7. Queue row/ciphertext corruption must stop sync and create diagnostics; the
   database must never be silently deleted or recreated.
8. Network flapping at request-body upload and response loss. Exact event replay
   must return the stored response and create one database event only.
9. Token expiry, revoked device, replacement device and stale activation code.
10. Supervisor conflict: stale revision returns conflict; maker cannot approve
    or lock their own submission.
11. Database restart during retry; Redis restart; restored database replay.
12. Battery and memory observation over a representative full shift.

## Evidence bundle

Store no employee PII, token, activation code or private key. The bundle must
include only device/model/build metadata, APK certificate fingerprint and hash,
scenario IDs, timings, sanitized logcat/DataWedge diagnostics, result, defect
reference and tester approval.

Passing emulator, unit or CI tests does not close a physical-device row.
