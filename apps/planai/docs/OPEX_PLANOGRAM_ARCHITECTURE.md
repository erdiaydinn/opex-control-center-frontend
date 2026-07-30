# OPEX-native Planogram architecture

## Runtime boundary

- OPEX route: `/planogram`
- Planogram API: `/api/planogram`
- Identity owner: OPEX Control Center
- Permission owner: OPEX Access Control
- Planogram admin owns only plan approvals, master-data review, data quality and audit.

Planogram never asks for a second username or password. The OPEX host sends the
current user's Planogram feature/action matrix and data scope to the embedded
runtime. The Planogram API still validates a signed bearer session on every
protected request.

## Local development

The current split runtime remains supported during migration:

- OPEX frontend: `http://localhost:5173`
- Planogram frontend: `http://localhost:5174`
- Planogram backend: `http://127.0.0.1:8001`

Because the OPEX prototype does not yet issue a server-signed access token,
non-production builds may use `/auth/opex-dev-exchange`. This endpoint:

- accepts requests only from configured local origins;
- is disabled unconditionally when `PLONAGRAM_ENV=production`;
- mints a short-lived signed Planogram token;
- carries the exact Planogram action matrix and warehouse scope.

## Production

Production must set `PLONAGRAM_ENV=production` and provide the centrally issued
OPEX bearer token. The reverse proxy should expose the module on one origin:

- `/planogram` -> Planogram frontend
- `/api/planogram/*` -> Planogram backend

The development exchange is unavailable in production even when its flag is
accidentally enabled. Frontend visibility is never treated as authorization;
state-changing API routes require action claims and store scope is checked by
the backend.
