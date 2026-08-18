# EAY Mobile Platform Architecture v1

## Decision

EAY Mobile becomes the platform execution layer. Web remains the command center; mobile executes work; Jarvis provides contextual intelligence. Mobile must not duplicate server authority.

Two product surfaces are canonical:

1. **EAY One** for employee/manager phones.
2. **EAY Terminal** for managed rugged/Zebra devices.

They share Mobile Core contracts but may have separate managed binaries, release rings and device policy.

## Migration instead of rewrite

`android-inventory` already contains production-oriented Android controls. It remains executable while its reusable contracts are extracted. The first extracted module is `android-inventory/mobile-core`. This avoids a security regression caused by replacing proven OIDC, Keystore, TLS pinning, encrypted queue, WorkManager and DataWedge behavior with an unproven greenfield shell.

## Mobile Core layers

- Identity context: tenant, actor, employee, location and auth binding.
- Device trust: registered/managed/hardware-bound state and integrity verdict.
- Policy snapshot: short-lived server-authoritative operation allowlist and fingerprint.
- Mission context: future task-oriented surface; modules are not the primary field navigation model.
- Event ledger: deterministic proof material, payload hash, sequence and previous-event hash.
- Sync: exact replay allowed; payload substitution and sequence collision denied; business conflicts must reconcile server-side rather than last-write-wins.
- Scanner: DataWedge hardware first for Terminal; camera can be a controlled adapter for One.
- Telemetry: operational health without raw credentials, barcode payloads, biometrics or precise location.
- Field design system: large targets, one-hand/glove operation, scan/audio/haptic feedback and minimal typing.

## Runtime invariant

A local allow decision is never equivalent to a server authorization. Mobile admission is an additional fail-closed edge control. The canonical backend must re-authorize all synchronized state mutation using current tenant, actor, device and policy state.

## First vertical acceptance path

`authenticated employee -> managed/trusted device -> active shift -> assigned mission -> count scan -> encrypted offline event -> reconnect -> server re-authorization -> exact idempotent commit -> supervisor reconciliation/approval -> append-only audit -> Jarvis explanation`

This path must pass before broad feature expansion. Picking, putaway, receiving, Planogram and Audit then reuse the same substrate.
