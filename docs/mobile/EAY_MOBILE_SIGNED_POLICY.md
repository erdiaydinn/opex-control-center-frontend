# EAY Mobile Signed Policy Contract v1

## Purpose

A mobile policy token protects the integrity of a short-lived edge/offline authorization snapshot. It is **not** a bearer authorization credential and never replaces current backend authorization on synchronized mutations.

## Cryptography

- Algorithm is fixed to ES256 (P-256 + SHA-256).
- Algorithm selection is never accepted from an untrusted token beyond an exact equality check.
- The token requires an explicit `kid` and a trusted public-key set.
- Production private signing keys must stay outside the application repository and outside mobile binaries. The production signer is a KMS/HSM-backed implementation of `MobilePolicySigningProvider`.
- EAY One/EAY Terminal receive only public verification material/keysets. Key rotation uses overlapping old/new public keys and bounded token TTL.

## Binding

Every signed token binds tenant, actor, device, installation, location, auth session, runtime profile, policy fingerprint, operation policies, issued/not-before/expiry times and deterministic token id.

Any mismatch between the verified token and the current local execution binding denies locally. The server independently re-authorizes every mutation.

## Lifetime

The signed policy lifetime is capped at five minutes and the canonical resolver defaults to two minutes. Critical operations remain online-only even if an operation is accidentally marked offline-capable elsewhere.

## Threats explicitly covered

- algorithm confusion / `none` downgrade;
- unknown or rotated key id;
- wrong signing key;
- payload tampering;
- replay into another device, installation, actor, tenant, location or auth session;
- expired/not-yet-valid/overlong policy;
- policy-fingerprint mismatch through the Mobile Core admission contract.

## Production truth

Repository unit tests validate the envelope contract, not production key custody. KMS/HSM key provisioning, rotation, revocation, mobile public-key distribution and disaster-recovery rehearsal remain external acceptance gates before `production_ready` may become true.
