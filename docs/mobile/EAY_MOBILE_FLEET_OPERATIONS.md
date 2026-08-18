# EAY Mobile Fleet Operations v1

## Principle

A field device must become observable before the operator reports a failure. Fleet telemetry is health evidence, not employee surveillance and not operation authorization.

## Privacy boundary

Routine fleet health contains no raw actor, employee, managed-device, installation, warehouse/location identifier, barcode, payload, token, biometric or precise coordinate. Device/site correlation uses opaque random server-issued tokens with no business meaning. Existing deterministic SHA-256 pseudonyms for raw employee/device identifiers are retired because low-entropy identifiers can be dictionary-tested.

## Health signal

The common observation contract includes only bounded operational signals:

- runtime profile and coarse device class;
- app version and rollout ring;
- online/offline state;
- pending and quarantined sync counts plus age;
- scanner health;
- recent crash/ANR counters;
- coarse battery bucket;
- observation time.

Classification is HEALTHY, DEGRADED or CRITICAL. Classification does not bypass policy or block/allow a business action; authority remains in Platform Core and Device Trust.

## Rollout rings

`DEVELOPER -> DOGFOOD -> LAB -> PILOT_1 -> PILOT_5 -> PILOT_20 -> 25% -> 50% -> 100%`

Optional new behavior is opt-in through a short-lived policy-bound Runtime Control snapshot. Missing, stale, policy-mismatched or unconfigured control means the optional feature remains disabled.

Runtime controls may govern only typed optional features such as new count UI, route assist, Planogram vision, Jarvis voice or Academy autoplay. Authentication, tenant isolation, device trust, certificate pinning, event integrity, encrypted storage, server authorization and offline policy are deliberately absent from the feature-control enum and cannot be remotely weakened by a client feature flag.

An empty enabled-ring set is the kill switch for an optional feature.

## Production truth

Repository tests prove the data-minimization and rollout-state contracts only. Production acceptance still requires a real telemetry ingestion endpoint, retention/access controls, DPA/KVKK review, alert thresholds calibrated from field baselines, crash/ANR integration, fleet dashboards, MDM ring assignment, rollback rehearsal and evidence from real devices.
