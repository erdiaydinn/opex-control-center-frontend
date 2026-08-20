# PR #134 — Operational Mobile Acceptance Cohort

This evidence note records repository-level acceptance criteria for the EAY Terminal operational mission cohort. It is not field-production proof and does not authorize a merge to `main`.

## Code cohort

The history-preserving operational hardening cohort immediately preceding this evidence carrier is `daecca8ba3b0f887cbb3d8214400bb5a2aecf638`.

The cohort extends the existing server-authoritative Inventory mobile runtime; it does not create client-owned tenant, employee, device, shift, mission, SKU, stock or permission truth.

## Executable mission set

| Mission | Governed physical order | Client input boundary |
| --- | --- | --- |
| Picking | SOURCE_LOCATION → ITEM → QUANTITY → CONTAINER → COMPLETE | Zebra scan → numeric → Zebra scan → explicit completion |
| Putaway | ITEM → QUANTITY → DESTINATION_LOCATION → COMPLETE | Zebra scan → numeric → Zebra scan → explicit completion |
| Receiving | CONTAINER → ITEM → QUANTITY → CONDITION → COMPLETE | Zebra scan → Zebra scan → numeric → server-frozen condition → explicit completion |
| Transfer | SOURCE_LOCATION → ITEM → QUANTITY → DESTINATION_LOCATION → COMPLETE | Zebra scan → Zebra scan → numeric → Zebra scan → explicit completion |

## Hardening in this cohort

- Exact operational event replay keeps the stored authoritative response and is surfaced as `idempotent_replay=true`; event-id payload substitution remains rejected.
- New non-Receiving typed mission intent no longer mints condition policy. Receiving alone owns non-empty `allowed_conditions` authority.
- Inventory v9 forward migration changes the typed condition scope without rewriting frozen v8 mission intent.
- Operational capture is serialized in the Android controller so rapid duplicate scanner/touch ingress cannot allocate concurrent durable step events.
- A rapid canonical duplicate of the immediately committed physical step is presentation-idempotent and allocates no second durable event/device sequence; a different canonical value remains fail-closed.
- Restart protection continues to hold any mission with unsettled operational evidence at `AWAITING_SERVER` or `REQUIRES_REVIEW` until signed sync and fresh server projection settle it.
- Mobile ACK still requires immutable shift + mission + claim attestation before local evidence is acknowledged.

## Repository acceptance gates

The candidate is not exact-head accepted until applicable GitHub Actions for the exact PR head are observed successful, including at minimum:

- EAY CI Admission Guard
- EAY Canonical Lineage Guard
- EAY Inventory Migration Contract
- EAY Inventory Production Gate
- OPEX Inventory Android
- EAY Mobile Field UI Compatibility
- EAY Mobile Platform Foundation

Any RED result is a blocker and must be repaired on the same canonical branch. Absence of a workflow result is not GREEN.

## Production truth boundary

Repository evidence does not prove corporate OIDC/revocation, protected managed signing/MDM lifecycle, Play Integrity, physical Zebra/DataWedge fleet configuration, certificate-pin rotation, real offline/online chaos, fleet telemetry, staged rollout/rollback or operator UAT.

Therefore this cohort keeps:

- `production_ready=false`
- `production_activation_permitted=false`
- `main_merge_permitted=false`
