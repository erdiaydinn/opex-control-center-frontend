# EAY Workforce/Hiring V31 production acceptance

Workforce and Recruitment use one canonical Employee Master. `employee_id` is
the durable primary identity; encrypted/hashed TC resolves identity changes,
and roster IDs remain unique aliases. Name, hire/exit dates, warehouse scope
and roster aliases are persisted in the same Workforce snapshot and audit
transaction. No parallel Hiring employee database exists.

## Transactional lifecycle gate

The accepted lifecycle is Norm → vacancy → candidate → evidence → human
approval/rejection → durable notification outbox → hire → Employee Master →
first shift. Hire activation is rejected unless the candidate has approved
evidence and a valid first shift on or after the hire date. Employee Master,
first shift, Recruitment vacancy revision, notifications and the hash-chained
audit record commit together or roll back together.

An exit makes the employee inactive, closes Workforce self-access, revokes
active device/enrollment/challenge authority, cancels future assigned shifts
and cancels pending push notifications. Existing historical attendance and
audit records are retained.

## Temporary September norms

The approved +1 set has `base_norm`, `temporary_adjustment=1`, effective window
`2026-07-01..2026-09-30` and `AUTOMATIC_REVIEW` reversion. On 2026-10-01 the
decision engine uses `base_norm` and reports `REVERTED_REVIEW_REQUIRED`; it does
not silently continue the +1 capacity.

## External field gates

| Gate | Required evidence | Current state |
|---|---|---|
| Corporate OIDC | Real issuer/audience plus `employee_id` and warehouse-scope claims; exit-token rejection | BLOCKED — tenant credentials required |
| Physical iOS/Android | Signed internal build, registered-device replacement, biometric presence without biometric storage | BLOCKED — devices/builds required |
| GPS/geofence | Interior, boundary, weak signal, multipath, spoof and accuracy-limit walk | BLOCKED — warehouse pilot required |
| Apple App Attest | Production key, genuine/replay/invalid verdict evidence | BLOCKED — Apple credentials required |
| Google Play Integrity | Production cloud project, genuine/replay/invalid verdict evidence | BLOCKED — Google credentials required |
| Customer imports | Case/punctuation/locale variants for Employee, TC, roster, attendance and leave columns | CI coverage; customer-format files pending |
| Staging DR | V29→V30→V31, load, restart, backup/isolated restore with measured RPO/RTO | CI rehearsal; operator staging evidence pending |

CI or emulator evidence cannot close any physical-device, corporate identity or
warehouse GPS row.
