# EAY Jarvis service-key bootstrap and rotation

This runbook covers only the EAY AI Core -> Platform Core machine identity.
It must not be reused for end-user OIDC or Identity Gateway `preauth` keys.

## Security invariants

- The P-256 private key remains outside Git and outside Platform Core.
- AI Core receives the private key only through its runtime secret mount.
- Platform Core receives public JWKS only.
- `kid` values are unique for distinct key pairs.
- A public JWKS must never contain the EC private coordinate `d`.
- Jarvis assertions use ES256, issuer `eay-ai-core`, audience
  `opex-core-jarvis`, and a 30-second lifetime.
- The Core verifier allows 5 seconds of clock leeway. Do not remove an old
  verification key until every old-key signer is stopped and at least
  **35 seconds** have elapsed since the last possible old-key assertion.
- Never retry an indeterminate single-use tool grant merely because a key
  rotation is occurring.

## Bootstrap

1. Provision an EC P-256 private key in the deployment secret manager or other
   approved secret store. Key generation/lifecycle remains outside this repo.
2. Assign a unique operational `kid`, for example `jarvis-2026-08-v1`.
3. From a controlled operator environment with read access to that private key,
   export public JWKS to a dedicated Platform trust directory:

```bash
python -m app.jarvis_jwks_export \
  --private-key-file /secure/eay/jarvis-private.pem \
  --kid jarvis-2026-08-v1 \
  --output /secure/platform/jarvis-trust/jarvis-service.jwks.json
```

The utility writes JWKS only to `--output`; it does not print key coordinates
or private material to stdout. Existing output is not overwritten unless
`--replace` is supplied explicitly.

4. Configure Platform Core:

```text
OPEX_JARVIS_SERVICE_JWKS_SOURCE_DIR=/secure/platform/jarvis-trust
```

Use `docker-compose.jarvis-trust.yml` only after the public JWKS exists.
5. Configure AI Core private-key source and matching `kid`:

```text
EAY_JARVIS_SERVICE_PRIVATE_KEY_SOURCE_FILE=/secure/eay/jarvis-private.pem
EAY_JARVIS_SERVICE_SIGNING_KID=jarvis-2026-08-v1
```

6. Start/recreate AI Core using the internal-only Jarvis profile. Do not publish
   port 8030 to the host and do not route it through the public gateway.

## Rotation: old key K1 -> new key K2

### 1. Provision K2 first

Create/provision a new P-256 private key in the approved secret store and give
it a new `kid`. Do not change running AI Core instances yet.

### 2. Publish overlap JWKS before changing the signer

Build a new public JWKS containing K2 plus the currently trusted K1:

```bash
python -m app.jarvis_jwks_export \
  --private-key-file /secure/eay/jarvis-private-v2.pem \
  --kid jarvis-2026-09-v2 \
  --merge-existing /secure/platform/jarvis-trust/jarvis-service.jwks.json \
  --output /secure/platform/jarvis-trust/jarvis-service.jwks.json.next
```

Review only public metadata (`kid`, algorithm, key count). Then atomically
replace the fixed trust filename in the same mounted directory:

```bash
mv /secure/platform/jarvis-trust/jarvis-service.jwks.json.next \
   /secure/platform/jarvis-trust/jarvis-service.jwks.json
```

Platform Core reads a bounded JWKS snapshot on each service assertion and
caches only identical public bytes, so an atomic file replacement is observed
without relying on stale path-only cache state.

### 3. Move AI Core signers to K2

Update the AI Core private-key secret source and
`EAY_JARVIS_SERVICE_SIGNING_KID` to K2. Roll/recreate AI Core instances so no
new assertion is signed by K1.

Do not remove K1 from Platform JWKS while any K1 signer remains active.

### 4. Drain the old assertion window

After the final K1 signer has stopped, wait at least **35 seconds** before
removing K1. This covers the 30-second assertion lifetime plus the verifier's
5-second clock leeway. Operational deployment propagation should be confirmed
in addition to this minimum cryptographic window.

### 5. Remove K1

Export a new-only JWKS from K2 and explicitly replace a staging output:

```bash
python -m app.jarvis_jwks_export \
  --private-key-file /secure/eay/jarvis-private-v2.pem \
  --kid jarvis-2026-09-v2 \
  --output /secure/platform/jarvis-trust/jarvis-service.jwks.json.next

mv /secure/platform/jarvis-trust/jarvis-service.jwks.json.next \
   /secure/platform/jarvis-trust/jarvis-service.jwks.json
```

K1 can then be retired according to the external secret-management retention
and incident-response policy.

## Rollback

If K2 signing fails before K1 has been removed, roll AI Core back to K1 while
the overlap JWKS still trusts both keys. Do not create a third ad-hoc key.

If the public JWKS becomes malformed or oversized, Platform Core fails closed
instead of falling back to a stale cached verification key. Restore the last
known-good **public** JWKS atomically; never copy a private key into the trust
directory.
