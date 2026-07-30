# Security Gates

## Local/dev allowed

- Wildcard CORS may be used only for local development.
- Demo credentials may exist only in local/dev context.

## Production requirements

- Default credentials disabled.
- Role authorization enforced by store scope.
- Store users cannot read or mutate other stores' Store DNA, readiness, planogram, or task data.
- Uploads validate extension, size, and parse failures.
- CSV formula injection is neutralized for exports.
- Error responses must not leak local paths, stack traces, credentials, tokens, or database internals.
- Every admin/user approval action is auditable.

## Required evidence before security claims

- Repro step
- Expected vs actual result
- Impact
- Fix
- Retest evidence
