# PR #134 — EAY Mobile Final Evidence Pack

This document is the repository-side evidence index for the canonical EAY Mobile / Inventory workstream. It records capability and truth boundaries without converting repository proof into field or production claims. Exact-current GitHub Actions run IDs are maintained in the PR #134 acceptance ledger because changing this file after a run would itself create a new, untested head.

## Authority

- Canonical PR: `#134`
- Canonical branch: `agent/eay-mobile-platform-foundation-v1`
- Base branch: `product/eay-category-leadership-v1`
- Base SHA observed before final acceptance cycle: `fbe527c836f55d19f30a86f1d4242ed571af3fb0`
- Session-recovery code SHA entering final acceptance: `abbb3ce572f6ce75d6113b4616329cccb267c4a3`
- Final exact head + Actions ledger: PR #134 body
- Composition policy: history-preserving fast-forward only; no force push/rebase; `main` remains untouched.

## Product evidence

### EAY One

- Separate Android application module: `android-inventory/eay-one-app`
- Application identity: `com.eay.one`
- Shared canonical runtime: `:field-ui-runtime`
- Separate auth/tenant/mission/inventory authority stack: **forbidden**
- Synthetic mission truth: **forbidden**
- INTERNET permission before reviewed corporate-session composition: **forbidden**
- Debug APK evidence is produced by `EAY Brand and One Host Contract` when the exact head passes.

### Explicit session recovery

EAY One now exposes a visible fail-closed corporate-session state using the canonical `FieldSessionRecoveryBannerModel` semantics:

- severity: `SECURITY`
- action intent: `SIGN_IN_AGAIN`
- user-visible action is localized across the supported EAY One locale resources
- current host does not launch AppAuth, a browser/deep link, a second OIDC flow, or a transport stack
- until the reviewed corporate-session adapter is composed, the action remains presentation-only and explains the authority requirement

This is a security UX improvement, not production authentication evidence.

### Inventory / field execution capability preserved

- Golden Count: server-authoritative SKU/location/task identity, attempt/lease ownership, device/employee/shift/warehouse binding, signed count + location-completion evidence, exact replay, duplicate-substitution rejection, recount lineage, quarantine and reconciliation truth.
- Picking / Putaway / Receiving / Transfer: server-frozen typed mission intent, signed device-bound claims/events, canonical step ordering, replay safety, reconciliation/outbox, maker-checker release and device-recovery authority.
- W2W v11-v13 authority is composed in the same canonical lineage, including closeout and operator/location ordering guards.
- Synthetic `EayMobilePreviewActivity` remains DEBUG-only and is not production evidence.

## Brand evidence

- Master: `EAY`
- Platform: `EAY One`
- Rugged field app: `EAY Terminal`
- Runtime external Google Fonts/CDN loading: forbidden by brand contract.

### Manrope admission

`typography.asset_state` remains `SELF_HOST_BINARY_PENDING`.

Reviewed upstream TTF provenance remains:

- `google/fonts:ofl/manrope/Manrope[wght].ttf`
- Git blob: `23dcf5e05a97f19a3567d40ebb3765580a4325f7`
- license: OFL-1.1

A smaller production-web admission path was additionally verified in `fontsource/font-files`:

- Latin variable WOFF2: `fonts/variable/manrope/files/manrope-latin-wght-normal.woff2`
  - Git blob: `71eb731d558046199aa7f985adbf812890a093a1`
  - size: 24,836 bytes
- Latin Extended variable WOFF2: `fonts/variable/manrope/files/manrope-latin-ext-wght-normal.woff2`
  - Git blob: `bd24140af06f1b5897d3bbd6538a74b03748a21e`
  - size: 15,120 bytes
- Fontsource Manrope license blob: `462280f3e4037df1839fba6cdee11d0980d3f0a9`

The connector can read these binaries as base64 but truncates the complete payload before a byte-identical target-repository write can be proved. No incomplete or substitute font was admitted. Therefore Manrope self-hosting remains **BLOCKED / NOT CLAIMED** rather than weakening the admission rule.

## Exact-current Actions acceptance policy

Final acceptance requires a literal-head cohort with no RED for the relevant PR #134 surface. The acceptance ledger in the PR body must record run IDs and conclusions for, as applicable:

- EAY CI Admission Guard
- EAY Canonical Lineage Guard
- EAY Inventory Migration Contract
- DockOS full-stack validation
- EAY Mobile Field UI Compatibility
- OPEX Inventory Android
- EAY Inventory Production Gate
- EAY Mobile Platform Foundation
- EAY Inventory Operational Runtime
- EAY Brand and One Host Contract
- EAY Inventory W2W V13

Historical or parent-head GREEN results are provenance only; they do not substitute for final exact-head proof.

## Previously identified regression and closure

The prior four Android-facing RED workflows shared one root cause: `android:windowLightNavigationBar` was placed in the base `values/` resource while minSdk remained 26. PostgreSQL authority, restart/restore, migration replay, web truth/build and mobile core/security jobs were GREEN. Commit `95506fdd08421f846dda1ad7f3a8753e83b83ae4` corrected the resource boundary using API-27-specific resources. Final exact-head Actions must still prove the fix in current composition.

## Readiness truth

- `repository_production_ready`: only after the exact-current acceptance ledger is GREEN
- `production_activation_permitted=false`
- `main_merge_permitted=false`

Repository proof does not manufacture field evidence. Production activation still requires the applicable corporate/physical acceptance inputs, including corporate OIDC and revocation behavior, managed signing/MDM, Play Integrity/App Attest, physical Zebra/DataWedge acceptance, GPS/geofence where required, certificate-pin rotation, KMS/HSM rehearsal, physical offline/online/network-flap tests, fleet telemetry, staged rollout/rollback, operator UAT, and downstream WMS consumer evidence where separately required.

## Final Demo & Sunum Standardı evidence classification

- Separate EAY One host: `REPOSITORY VERIFIED` only after exact-current Actions GREEN
- EAY One session-recovery UX: `REPOSITORY VERIFIED` only after exact-current Actions GREEN
- Mobile/Inventory authority contracts: `REPOSITORY VERIFIED` only after exact-current Actions GREEN
- Real corporate authentication / device / field execution: `NOT CLAIMED` until external acceptance evidence exists
- Manrope self-host binary: `BLOCKED / NOT CLAIMED`
