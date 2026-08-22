# EAY Mobile Fleet Operations v1

## Principle

A field device must become observable before the operator reports a failure. Fleet telemetry is health evidence, not employee surveillance and not operation authorization.

## Privacy boundary

Routine fleet health contains no raw actor, employee, managed-device, installation, warehouse/location identifier, barcode, payload, authentication/session token, biometric or precise coordinate. Device/site correlation uses opaque server-issued correlation tokens with no business meaning. A device correlation token is random. A site correlation token is keyed and one-way so raw site identifiers are never sent in routine telemetry. Existing unkeyed deterministic SHA-256 pseudonyms for raw employee/device identifiers remain prohibited because low-entropy identifiers can be dictionary-tested.

Telemetry payload validation is fail-closed. Unknown fields are rejected, so adding `employee_id`, `device_id`, raw barcode, coordinates or a client-supplied health verdict cannot silently expand the data surface.

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

Classification is `HEALTHY`, `DEGRADED` or `CRITICAL`. The server derives the classification from the observation; the client cannot submit its own health result. Classification does not bypass policy or block/allow a business action; authority remains in Platform Core and Device Trust.

## Fleet proof and provisioning

`POST /v1/mobile/fleet/credentials` is restricted to the existing Workforce `manageDevices` authority. It issues:

- a random opaque device correlation token;
- an optional one-way opaque site correlation token;
- a bounded fleet proof tied to tenant, runtime profile, rollout ring, device token and site token.

The raw site binding is used only while issuing the correlation material and is neither returned nor stored in fleet health. The proof carries no operation permission. Changing tenant, runtime profile, rollout ring, device token or site token invalidates the proof. Production delivery of the issued material must use managed configuration/MDM and protected application storage.

## Ingestion, replay and retention

`POST /v1/mobile/fleet/health` requires both an authenticated active tenant principal and a valid fleet proof. Observations that are stale, excessively future-dated or proof-mismatched fail closed.

Fleet storage is deliberately latest-snapshot only:

- Redis retains one latest snapshot per opaque device token;
- snapshot/index TTL is 48 hours;
- same timestamp + same payload is an idempotent replay;
- same timestamp + different payload is rejected;
- an older observation cannot replace a newer observation;
- the Redis update/replay decision is atomic;
- fleet proof material is never persisted in the health snapshot.

This is intentionally not a workforce history store. Long-term employee movement or device-to-employee surveillance data does not belong in this telemetry path.

`GET /v1/mobile/fleet/health` is tenant-scoped and requires the existing Workforce devices-view permission. It returns only bounded latest snapshots and server-derived health.

## Rollout rings

`DEVELOPER -> DOGFOOD -> LAB -> PILOT_1 -> PILOT_5 -> PILOT_20 -> 25% -> 50% -> 100%`

The fleet proof binds the declared rollout ring so a client cannot promote itself by changing the payload. Optional new behavior remains opt-in through a short-lived policy-bound Runtime Control snapshot. Missing, stale, policy-mismatched or unconfigured control means the optional feature remains disabled.

Runtime controls may govern only typed optional features such as new count UI, route assist, Planogram vision, Jarvis voice or Academy autoplay. Authentication, tenant isolation, device trust, certificate pinning, event integrity, encrypted storage, server authorization and offline policy are deliberately absent from the feature-control enum and cannot be remotely weakened by a client feature flag.

An empty enabled-ring set is the kill switch for an optional feature.

## Production truth

The repository now contains the privacy-bounded ingestion, proof binding, server classification, latest-snapshot retention and tenant-scoped read contracts. That is repository/integration evidence only, not field or production acceptance.

Production activation still requires:

- fleet proof secret in a managed secret/KMS authority with rotation rehearsal;
- real MDM delivery/revocation of fleet credentials and rollout-ring assignments;
- Android reporter scheduling plus crash/ANR and scanner-health integrations on real builds;
- telemetry ingestion load/failure testing and calibrated alert thresholds from field baselines;
- fleet dashboards and alert routing;
- DPA/KVKK retention/access review;
- rollback rehearsal and evidence from real devices.

Fleet telemetry never grants Inventory, Workforce, Picking, Receiving, Putaway, Transfer or any other operational authority.
