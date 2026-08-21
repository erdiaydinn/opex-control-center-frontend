# OPEX Enterprise Architecture v1

## 1. Product definition

OPEX Control Center is a multi-tenant, modular operations platform. One codebase serves many customer organizations while keeping identity, data, configuration, branding, licensing and audit history isolated.

This document is the architectural contract for Platform Core 1.0. Feature work must not bypass these rules.

## 2. Non-negotiable principles

1. Tenant isolation is enforced by the backend and database, never only by the browser.
2. Every protected request has an authenticated actor, tenant context, request ID and authorization decision.
3. The frontend is untrusted. Hidden routes, buttons or API URLs are not security controls.
4. Customer data is never used across tenants unless an explicit platform-level workflow is authorized and audited.
5. Critical actions are deny-by-default, least-privilege and auditable.
6. Secrets never enter source control, frontend bundles, logs or error responses.
7. Every schema and API change is versioned, tested and reversible.
8. AI is local-first. External token usage is disabled by default and can only be enabled per tenant by policy.
9. AI may recommend; deterministic services validate. High-impact actions require human approval.
10. Production changes pass automated checks before deployment.

## 3. Target topology

```text
Internet / Customer Network
          |
      Edge Gateway
  TLS, WAF, rate limits
          |
  +-------+-------------------+
  |                           |
Frontend SPA              Core API
                          auth / tenant / RBAC
                              |
              +---------------+----------------+
              |               |                |
          PostgreSQL        Redis         Object Storage
          RLS + audit       cache/jobs     documents/media
                              |
                        Workflow Workers
                              |
                         Jarvis AI Router
                       local Ollama by default
```

The first implementation uses Docker Compose. Services remain independently deployable so the same design can later move to Kubernetes without rewriting business modules.

## 4. Tenant model

A tenant represents a customer organization such as a restaurant chain, retailer or logistics company.

Every tenant-owned database table must contain `tenant_id` and use PostgreSQL Row-Level Security. The API sets the database session tenant before executing tenant-scoped queries. Application filters alone are not accepted as the final isolation boundary.

Hostnames map to tenants through a verified domain table:

- `customer-a.opex.example`
- `operations.customer.com`
- temporary IP or localhost access during development

Custom domains change branding and tenant resolution, not the codebase.

Platform administrators operate through a separate platform scope. Cross-tenant support access must be time-limited, reason-bound and written to the audit log.

## 5. Identity and authorization

Production authentication uses an OpenID Connect provider. The API validates issuer, audience, signature, expiry and token type. Passwords are not stored in the frontend.

Authorization combines:

- tenant membership
- role
- module entitlement
- action permission
- resource scope such as region, warehouse, supplier or cost center
- optional policy conditions

A typical permission is expressed as:

```text
inventory.count.approve
scope: warehouse in [TR-IST-001, TR-IST-004]
```

The backend is the source of truth. Frontend permission checks only improve user experience.

## 6. Module licensing

Each tenant has explicit entitlements. A module can be enabled independently or as a bundle.

Initial module keys:

- `workforce`
- `inventory`
- `planogram`
- `dockos`
- `budget`
- `academy`
- `insight`
- `platform_health`

The API rejects access when a tenant lacks the module entitlement even if the user has a matching role.

## 7. Audit and observability

Every sensitive action records:

- event ID
- timestamp
- tenant ID
- actor ID
- action
- resource type and ID
- request ID
- source IP and user agent where lawful
- before/after summary with secret and personal-data redaction
- decision result
- approval reference when applicable

Logs are structured JSON. Metrics cover latency, errors, queue depth, database health, backup age and tenant-level usage without exposing tenant data.

## 8. API security

The API cannot be meaningfully hidden from a browser. It must remain safe when its routes are known.

Required controls:

- TLS in transit
- signed short-lived access tokens
- backend authorization on every protected route
- tenant context validation
- schema validation and payload limits
- per-user, per-tenant and per-IP rate limits
- idempotency keys for critical writes
- CSRF protection when cookie authentication is used
- strict CORS allowlists
- secure response headers
- no secrets or stack traces in responses
- dependency and container scanning
- audit logging and anomaly detection

API obfuscation may reduce casual discovery but is never treated as a security boundary.

## 9. Data protection

- PostgreSQL encryption at rest is provided by the hosting layer or encrypted volumes.
- Highly sensitive fields use application-level envelope encryption where needed.
- Backups are encrypted, versioned and regularly restored in a test environment.
- Retention and deletion policies are tenant-configurable within legal requirements.
- Personal data collection follows data minimization. Biometric data is not a default requirement for workforce check-in.

## 10. Workforce check-in direction

Check-in must use layered evidence rather than pretending one signal is fraud-proof. Supported controls can include registered device binding, rotating site QR codes, geofence policy, network/site validation, shift window, device integrity signal and supervisor exception flow.

Every check-in decision stores the policy version and evidence used. Customers choose the lawful policy appropriate to their workforce and jurisdiction.

## 11. Jarvis architecture

Jarvis is a permission-aware operations agent, not a direct database chatbot.

```text
User request
  -> intent and policy check
  -> authorized tools
  -> deterministic data services
  -> local model reasoning / summarization
  -> proposed action plan
  -> human approval when required
  -> workflow execution
  -> audit record
```

The AI layer receives only data the actor is authorized to access. Tenant ID and permissions are rechecked at every tool call.

Default provider policy:

- local Ollama: enabled
- external model providers: disabled
- external fallback: explicit tenant opt-in, budget limit and data policy required

The model provider is replaceable. Business workflows do not depend directly on one model vendor.

## 12. Delivery stages

### Platform Core 1.0

- Docker Compose development topology
- Core API skeleton
- PostgreSQL and Redis
- configuration validation
- request correlation and security headers
- tenant request context contract
- health/readiness endpoints
- CI build checks
- architecture and security records

### Platform Core 1.1

- OIDC integration
- tenant, membership, role, entitlement and audit schema
- PostgreSQL RLS migrations
- policy authorization service
- frontend API session migration
- integration tests proving cross-tenant denial

### Platform Core 1.2

- domain and white-label configuration
- rate limiting
- background jobs
- object storage
- backup/restore automation
- Platform Health UI

### Intelligence Core

- local Ollama provider
- AI router
- RAG with tenant-scoped retrieval
- tool approval workflow
- evaluation, tracing and prompt versioning

## 13. Definition of done

A Platform Core change is complete only when:

- code and configuration are committed together
- automated tests pass
- production-dangerous defaults fail closed
- tenant isolation tests pass where relevant
- migration and rollback paths exist
- logs contain request context but no secrets
- documentation matches the implementation
- deployment health checks pass

## 14. Immediate decision

The existing browser-local access configuration remains a prototype only. It must not be described or deployed as enterprise authentication. Migration will preserve the current UI while moving identity, tenancy, permissions and data enforcement into the Core API.
