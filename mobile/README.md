# EAY Mobile Platform

EAY Mobile is the field-execution layer of the EAY Platform. It is not a responsive copy of the web command center.

## Product surfaces

- **EAY One** — employee/manager phone experience: Today, shift, missions, approvals, Academy, Planogram capture, Audit and Jarvis.
- **EAY Terminal** — managed rugged/Zebra experience: picking, cycle count, receiving, putaway, transfer and scanner-first warehouse flows.

The surfaces share one security, policy, event, sync, telemetry and design foundation, but are allowed to ship as different managed application binaries when device policy or field ergonomics requires it.

## Migration rule

The proven `android-inventory` application is the first EAY Terminal migration source. We do not rewrite it from scratch. Mobile Core is extracted behind compile/test gates, then EAY One and the remaining terminal features consume the same contracts. This preserves OIDC/PKCE, managed-device identity, Keystore request proof, certificate pinning, encrypted offline state, replay/idempotency protection and DataWedge behavior already present in the terminal.

## Non-negotiable authority boundary

The phone is never the source of truth for tenant, permissions, inventory state, approvals or production policy. A cached authorization snapshot exists only to bound UX/offline behavior; every synchronized mutation is re-authorized by the canonical backend. Missing, expired, mismatched or unverifiable authority denies.

Current state is **foundation only**. Repository/CI evidence is not physical-device, field or production acceptance. See `config/eay_mobile_platform.json` and `docs/mobile/`.
