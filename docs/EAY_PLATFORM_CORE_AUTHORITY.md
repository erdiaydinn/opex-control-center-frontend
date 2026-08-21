# EAY Platform Core Authority Contract

Status: repository-enforced architecture boundary. This document is not production identity evidence.

## Goal

Platform Core is the final authorization authority for browser-facing EAY product workflows. Identity Gateway or an external OIDC provider may authenticate an identity, but authentication alone never grants tenant, role, permission or resource-scope authority.

Canonical flow:

`verified identity -> Core tenant membership -> DB roles/permissions -> Core permission scope -> product module`

A module may translate canonical scope dimensions into domain vocabulary, but it may not reinterpret raw permission assignments or invent its own unrestricted semantics.

## Authority ownership

- Identity authentication: Identity Gateway / verified OIDC input.
- Final tenant + membership + roles + permissions: `app.core.security.get_current_principal` backed by `resolve_principal_access`.
- Resource scope: `app.core.authorization.resolve_permission_scope`.
- Locale matrix and RTL direction: `app.core.localization`.
- Shared notification transport: `services/platform-alerts`; commercial modules must not embed SMTP/push provider transports.
- HTTP authority audit: Core audit middleware/shared audit sink. Product modules may have domain history but must not create a second platform authority audit database.

## Browser trust boundary

Browser/client values may be presentation or request data but are never authorization inputs for:

- tenant identity
- membership
- role
- permission
- resource scope
- authorization fingerprint

Tenant/scoped routes derive tenant from the verified `Principal`. A route accepting tenant authority through query parameters, custom `X-Tenant-*` headers or module-defined session state is a contract violation.

## Scoped permission semantics

Core accepts only DB-derived permission assignments. The exact scope `{ "type": "all" }` means unrestricted. Any ambiguous `type` object is invalid and fails closed. Other dimensions must be lists of non-empty strings and are unioned across assignments for the same permission.

A flattened permission with no matching scope assignment is an authority inconsistency and fails closed rather than becoming an unscoped grant.

## Localization

The single runtime locale contract is:

`tr, en, de, ar, fr, es, it, nl, pl, pt-BR`

Arabic is RTL. Modules import the shared locale contract instead of defining a competing set. Physical identifiers and operational truth values are not translated merely because labels are localized.

## Notification boundary

`platform-alerts` remains the shared transport authority. Module code may create a governed intent/workflow event, but must not directly own SMTP, SendGrid or Firebase transport. Universal notification-center behavior is a later product layer; this contract prevents per-module transport forks now.

## Audit boundary

Core binds HTTP audit events to verified actor, tenant and request context. A module may persist its own business history (for example approval history or evidence lifecycle), but may not write a parallel `audit_events` platform sink or reconstruct actor/tenant from client payload.

Audit durability for high-risk transactional writes is a separate production-hardening acceptance requirement; this repository contract does not claim that external production evidence already exists.

## CI enforcement

`EAY Platform Core Authority` fails when a Core product module:

- reads `principal.permission_assignments` directly;
- accepts tenant authority from headers or query parameters;
- defines a competing locale matrix;
- embeds direct SMTP/SendGrid/Firebase transport;
- creates or writes a competing platform `audit_events` sink.

Adversarial tests prove these violations are detected rather than merely documenting the intended rule.

## Production truth

Repository enforcement is only software evidence. Corporate OIDC claim mapping, workload identity, real notification delivery, managed-device identity where applicable and production/staging audit/DR evidence remain external gates. `production_ready=false` and production activation remains forbidden until those real gates pass.
