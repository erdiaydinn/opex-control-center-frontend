# EAY Mobile Acceptance Gates v1

A feature is not accepted because its screen works. It must pass the relevant gates below.

## G0 — lineage and no-regression

- Built from the canonical non-main EAY continuation.
- Frozen AI Core PR #15 and Security PR #16 untouched.
- Existing Inventory OIDC, managed identity, Keystore proof, pinning, encrypted offline queue, replay protections and DataWedge contracts preserved.
- No direct main merge or production activation.

## G1 — identity / tenant / authorization

- Missing server policy denies.
- Tenant, actor, location, device and auth binding must match exactly.
- Expired policy denies.
- Client-side role/permission text never grants authority.
- Server re-authorizes every synchronized mutation.

## G2 — device / integrity

- Managed-device lifecycle tested: enroll, activate, rotate, lost device, replacement, revoke.
- Hardware-backed key proof validated server-side.
- Real Play Integrity genuine/replay/invalid verdicts tested.
- Rooted/tampered/unrecognized policy follows explicit fail-closed production rules.

## G3 — offline / replay / conflict

- Offline queue survives process death and device reboot.
- Exact replay is idempotent.
- Same event id with changed payload is rejected.
- Same device sequence with a different event is rejected.
- Auth/session change cannot replay the old queue silently.
- Concurrent count/stock conflicts require server reconciliation; no blind last-write-wins.
- Queue corruption is visible and fail-closed.

## G4 — transport / secret handling

- Production endpoint HTTPS and active+backup certificate pins verified.
- Pin rotation rehearsal passes.
- Tokens, keys, raw payloads, barcodes, biometrics and precise location are absent from telemetry/crash evidence.
- Release signing is protected and reproducible enough to verify artifact provenance.

## G5 — field ergonomics and localization

- Zebra hardware scanning matrix passes for required device families.
- Scan-to-feedback, gloves, one-hand use, low light, sun visibility and accidental double-scan scenarios pass.
- Accessibility includes large targets, screen semantics, contrast and non-color-only status.
- Critical flow avoids unnecessary typing and modal navigation.
- The shared Platform Core localization contract is used; a module-specific locale list is not accepted.
- Production resource-key parity passes for TR, EN, DE, AR, FR, ES, IT, NL, PL and PT-BR.
- Locale plural categories satisfy the shared CLDR cardinal contract and Android lint.
- RTL is locale-driven; feature code may not force LTR. Arabic RTL field flows require visual acceptance.
- A new mobile feature cannot claim production acceptance with an English-first localization exception.

## G6 — resilience / fleet

- Network loss before/during/after scan.
- Token expiry during queued sync.
- backend 4xx/5xx, timeout, restart and network flapping.
- 10k queued-event stress profile.
- low battery / background restrictions.
- fleet health includes app version, device class, sync depth/latency, scanner health, crash/ANR and rollout ring without leaking protected payloads.

## G7 — rollout

`developer -> dogfood -> lab device -> 1 pilot store -> 5 stores -> 20 stores -> 25% -> 50% -> 100%`

Each ring has stop/rollback criteria and remote kill switches for non-security feature behavior. Server security policy cannot be weakened by a client flag.

## Production truth

Repository tests can close internal software gates only. Production readiness additionally requires corporate identity, managed signing/MDM, physical devices, real endpoint pins, real integrity credentials, field walking, operator UAT and production-shape fleet evidence. Until then the canonical platform flag remains false.
