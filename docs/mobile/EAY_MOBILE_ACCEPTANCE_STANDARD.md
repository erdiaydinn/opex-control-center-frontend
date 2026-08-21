# EAY Mobile acceptance bar

The downloadable EAY Mobile preview must not be offered merely because an APK compiles.

## Product bar

- One native EAY Mobile launcher, with EAY One for phone workflows and an explicit managed EAY Terminal hand-off.
- Today, Missions, Scan, Jarvis and Me are real navigable surfaces rather than placeholder buttons.
- Workforce, Golden Count, Picking, Putaway, Receiving, Transfer, Planogram, Audit and Academy have coherent native detail/execution surfaces.
- Count and physical inventory workflows reuse the canonical server-authoritative execution path in real terminal mode. Preview content is DEBUG-only and never manufactures production authority.
- Light/dark theme, RTL-safe layout, 56/64dp touch targets, meaningful progress/status surfaces and accessibility semantics remain intact.
- Synthetic preview data is visually marked and cannot mutate stock, shift, device, identity, evidence or reconciliation truth.

## Security bar

- No client-owned tenant, identity, device, shift, mission, permission, expected-stock or reconciliation authority.
- No raw credential or barcode persistence in presentation models.
- Managed-device, signed-event, replay/idempotency, offline queue and quarantine contracts remain unchanged.
- Release builds do not expose synthetic missions.

## Verification bar

A candidate is not offered for installation until:

1. Android assemble + lint succeeds on the exact candidate snapshot.
2. Field UI static/localization contract succeeds with canonical 10-locale + RTL coverage.
3. Mobile security/foundation gates succeed without weakening checks.
4. Inventory operational runtime and production gate succeed for the exact candidate or a newer descendant that preserves the same mobile tree.
5. The build artifact is produced from an immutable/stable snapshot and its source SHA is recorded.

Repository acceptance is not physical-fleet acceptance. Corporate OIDC, MDM/signing, Play Integrity/App Attest, Zebra/DataWedge hardware behavior, certificate-pin rotation and physical offline/network tests require environment evidence before production activation.
