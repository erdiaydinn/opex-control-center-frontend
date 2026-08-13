# EAY Workforce/Hiring V32 acceptance continuation

V32 continues PR #61's single Employee Master and does not create a second
Hiring identity store. The authoritative contract is:

`TC digest/encrypted value → employee_id → unique roster_ids → warehouse/store scope → employment dates`

Recruitment activation requires an approved candidate, at least one roster ID
and a first shift bound to one of those roster IDs. Norm → vacancy → candidate
→ evidence → approval/rejection → durable mail outbox → hire → Employee Master
→ first shift remains one audited lifecycle. The approved temporary +1 norm set
and its `2026-09-30` end date remain unchanged; from `2026-10-01` the base norm
is used with `REVERTED_REVIEW_REQUIRED`.

## Closed operational gaps

- Customer Employee/TC/roster/attendance/leave headers are normalized in the
  API independent of Turkish case, punctuation and common spelling variants.
- Attendance above 11 net hours is retained and flagged. Approved leave never
  hides work; leave-only, work-only and leave+work conflict days remain visible
  through `/api/workforce/daily-status`.
- Future-dated exits keep current access but cancel shifts and notifications on
  or after the exit date. On the effective date the employee, device,
  enrollment and challenge are closed.
- Effective exits atomically enqueue an idempotent, tenant-RLS protected
  corporate OIDC/session revocation. Retry/dead-letter delivery is performed by
  `workforce_identity_revocation_worker.py`; due exits are applied by
  `workforce_employment_lifecycle_worker.py`.

## External acceptance gates (cannot be closed by CI)

| Gate | Required field evidence | State |
|---|---|---|
| Corporate OIDC | Production issuer/audience; real `employee_id` and `warehouse_scope` claims; stale-token and exit-revocation proof | BLOCKED — tenant/IdP credentials |
| iOS | Signed internal build; physical Face ID/passcode presence; App Attest genuine/replay/invalid verdicts; device replacement/loss | BLOCKED — Apple credentials/devices |
| Android | Signed internal build; physical biometric/PIN presence; Play Integrity genuine/replay/invalid verdicts; device replacement/loss | BLOCKED — Google credentials/devices |
| Warehouse GPS | Interior, boundary walking, weak signal, multipath, accuracy rejection and spoof/failure observations | BLOCKED — pilot warehouse/devices |
| Customer HR files | Real customer employee, roster, leave and attendance files with reconciled expected totals | BLOCKED — customer samples |
| Staging PostgreSQL/DR | V29→V32 rehearsal, concurrent load, restart, backup/isolated restore and measured RPO/RTO | CI rehearsal; operator staging proof pending |

Production health is deliberately degraded unless the OIDC claim mappings,
exit-revocation adapter and attestation gateway credentials are configured.
No biometric image/template and no continuous off-shift location are stored.
