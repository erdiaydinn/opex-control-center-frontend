# Security Policy

## Security-first release policy

EAY treats security acceptance as a release requirement. Customer requests are not the trigger for testing: repository adversarial checks, authorized non-production staging checks, and independent penetration testing are expected before production/customer acceptance for security-sensitive releases.

## Reporting a vulnerability

Do not open a public GitHub issue containing secrets, personal data, exploitable credentials, candidate documents, employee records, or detailed reproduction material for a security vulnerability.

Use a private, access-controlled security reporting channel agreed with the repository owner. Include only the minimum sanitized evidence needed to reproduce the issue.

## Authorized testing boundary

Testing against EAY systems requires explicit authorization for the exact target and environment.

Unless a written scope explicitly says otherwise:

- production is out of scope;
- denial of service, load exhaustion, phishing/social engineering, credential stuffing against real users, persistence and destructive testing are prohibited;
- third-party systems are out of scope;
- synthetic accounts/test tenants must be used;
- real PII, TC numbers, candidate documents, customer data and secrets must not be intentionally collected or retained.

The repository staging harness is intentionally low impact and refuses production-looking, non-HTTPS, or non-allowlisted targets.

## Security gates

Main-bound changes are expected to pass the EAY Pre-Pentest Security Acceptance and applicable platform/release CI on the exact candidate head. Security-critical findings are not waived by stale CI evidence.

Critical and High findings from an independent penetration test are release blockers until remediation and retest are complete.

## Security-sensitive areas

Extra review attention is required for:

- authentication, authorization, OIDC/JWT/session handling;
- tenant/store/warehouse/employee scope enforcement;
- Workforce attendance, leave, shift, roster and offboarding authority;
- Hiring candidate evidence, scanner, official-document integration and lifecycle transitions;
- PostgreSQL roles/RLS and migrations;
- device trust, GPS/geofence, App Attest/Play Integrity boundaries;
- upload/download/storage and encryption/KMS boundaries;
- audit/outbox integrity and replay/idempotency;
- CI/release workflows, secrets and deployment configuration.

See `docs/security/EAY_EXTERNAL_PENTEST_SCOPE_V1.md` for the independent assessment scope and evidence standard.
