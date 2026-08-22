# EAY Mobile Security Model v1

## Zero-trust mobile boundary

A mobile device is an untrusted execution edge until server evidence proves otherwise. UI state, local role labels, cached tenant text, device clock and network origin never grant authority.

## Required binding

Sensitive operations bind exactly to:

`tenant + actor + employee + location + device + installation + auth session + active shift where required + policy fingerprint + operation + payload hash`

A mismatch denies. High-risk operations require a passing integrity verdict. Medium-or-higher risk requires a managed device. Critical operations are online-only.

## Identity and session

Corporate OIDC Authorization Code + PKCE remains the interactive identity path. Refresh material is encrypted at rest; access tokens are memory-bounded. Exit/revocation and stale claim behavior are server concerns and must be field-tested. No embedded username/password flow is permitted.

## Device identity and proof

Stable device identity is MDM/enrollment-owned. Hardware-backed Keystore signing proves possession of the enrolled installation key. Device identifiers supplied only by the client are not trusted as authority. `ANDROID_ID` is not canonical EAY device identity.

## App/device integrity

Play Integrity is a required Android production signal for protected operations, but is not sufficient authorization by itself. The backend combines integrity verdict, enrollment state, key proof, OIDC identity, tenant scope and policy. Replay/invalid verdicts must be tested with real credentials before production readiness can become true.

## Network

Production API and OIDC endpoints require HTTPS. Warehouse APIs retain certificate pinning with active and backup pins. Redirects or alternate origins must not silently bypass the trusted origin. Pin rotation must be rehearsed before rollout.

## Offline

Offline is bounded execution, not offline authority. Only operations explicitly granted in a short-lived server policy snapshot may queue offline. Critical approvals never execute offline. Each event carries canonical payload hash, stable event id, per-device sequence, auth binding and ledger linkage. Exact replay is safe; payload substitution, sequence collision, auth-binding mismatch or ledger corruption fail closed.

## Data at rest

Sensitive queued state remains encrypted. Secrets are excluded from logs, analytics and crash metadata. Biometric images/templates are not stored by Mobile Core. Precise location is used only where policy requires it and must not be emitted as routine telemetry.

## Telemetry privacy

Raw access/refresh/id tokens, Authorization headers, signatures, payloads, barcodes, national identifiers, biometric data and precise coordinates are forbidden in telemetry. User/device identifiers are fingerprinted where correlation is necessary.

## Jarvis

Jarvis receives bounded context, not unrestricted mobile storage. Informational copiloting is separated from state-changing agent execution. Any action still passes canonical server policy, authorization, approval where required and audit. Jarvis cannot bypass maker-checker, tenant isolation or device trust.

## Truth boundary

Green repository CI demonstrates software contracts only. Corporate OIDC, real integrity verdicts, physical Zebra scanners, MDM, signing, field GPS, certificate pins and offline/online chaos remain external evidence. `production_ready=false` until they pass.
