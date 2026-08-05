# OPEX Platform Core Runbook

This runbook covers the new Docker-based platform foundation. It does not replace the legacy PlanAI runbook until PlanAI frontend and backend are migrated into the platform topology.

## 1. Current service truth

The platform branch starts:

- Edge gateway
- OPEX frontend
- OPEX Core API
- PostgreSQL
- Redis
- Optional Ollama

The following legacy services are not yet containerized in this stack:

- PlanAI frontend on port 5174
- PlanAI backend on port 8001

The `/planogram` experience may therefore still require the legacy services described in `docs/LOCAL_RUNBOOK.md`.

## 2. Prerequisites

- Docker Desktop with Docker Compose v2
- Git
- At least 8 GB RAM for the base stack
- Additional memory appropriate to the selected local AI model when the `ai` profile is enabled

A company-owned domain is not required for local or pilot startup. The gateway is reachable through the machine IP and configured port. Production internet exposure still requires approved TLS, DNS or a secure private-network ingress.

## 3. First start

From the repository root:

```powershell
Copy-Item .env.example .env
```

Change at least `OPEX_POSTGRES_PASSWORD` in `.env`. Keep the password consistent inside `OPEX_DATABASE_URL`.

Start the base platform:

```powershell
docker compose -f docker-compose.platform.yml up --build -d
```

Check status:

```powershell
docker compose -f docker-compose.platform.yml ps
```

Open:

```text
http://localhost:8080
```

Gateway health:

```text
http://localhost:8080/gateway-health
```

Core API liveness through the gateway:

```text
http://localhost:8080/api/health/live
```

Core API readiness through the gateway:

```text
http://localhost:8080/api/health/ready
```

## 4. Development authentication check

Development tokens are accepted only when:

```text
OPEX_AUTH_MODE=development
OPEX_ENVIRONMENT is not production
```

Example PowerShell request:

```powershell
$headers = @{
  Authorization = "Bearer dev.user-1.tenant-a.platform_admin"
}

Invoke-RestMethod `
  -Uri "http://localhost:8080/api/v1/context" `
  -Headers $headers
```

Expected response includes:

- actor `user-1`
- tenant `tenant-a`
- role `platform_admin`
- request ID

Development tokens are not passwords and are not production authentication. Production refuses to start with development authentication enabled.

## 5. Start local AI

Ollama is optional and external AI is disabled by default.

Start the AI profile:

```powershell
docker compose -f docker-compose.platform.yml --profile ai up -d ollama
```

Pull the configured model:

```powershell
docker compose -f docker-compose.platform.yml exec ollama ollama pull qwen3:8b
```

The model name must match `OPEX_OLLAMA_MODEL`.

The current foundation starts Ollama infrastructure only. Jarvis workflows, tenant-scoped retrieval and tool approval are separate implementation stages. Do not describe the current stack as a completed AI agent.

## 6. Logs

All services:

```powershell
docker compose -f docker-compose.platform.yml logs -f
```

Core API only:

```powershell
docker compose -f docker-compose.platform.yml logs -f core-api
```

Gateway only:

```powershell
docker compose -f docker-compose.platform.yml logs -f gateway
```

Database only:

```powershell
docker compose -f docker-compose.platform.yml logs -f postgres
```

## 7. Normal shutdown

```powershell
docker compose -f docker-compose.platform.yml down
```

This keeps named volumes.

## 8. Destructive local reset

The following deletes the local PostgreSQL, Redis and Ollama volumes:

```powershell
docker compose -f docker-compose.platform.yml down -v
```

Use it only for disposable development data. Never use this as a production recovery procedure.

## 9. Configuration rules

- Never commit `.env`.
- Never put API keys, passwords or private credentials in frontend variables.
- Production must use `OPEX_AUTH_MODE=oidc`.
- Production CORS must list exact approved origins.
- Custom customer domains must be verified and mapped to a tenant before use.
- External AI remains disabled unless a tenant policy, data policy and budget explicitly enable it.
- Real customer data must not be used while the repository visibility and sanitization security issue remains open.

## 10. No-domain pilot access

For a controlled local network pilot, another device may connect to:

```text
http://<host-machine-lan-ip>:8080
```

Required conditions:

- host firewall permits the chosen port
- the network is trusted or protected by VPN
- `OPEX_ALLOWED_HOSTS` contains the approved host or IP
- the test contains no production-sensitive data unless TLS and the production security controls are complete

Do not expose port 8080 directly to the public internet as the final production design.

## 11. Customer-domain target

Later, the edge layer will map verified domains such as:

```text
operations.customer-a.com
control.customer-b.com
```

to tenant records. Branding, licensed modules and policy will load from the resolved tenant. A new customer must not require a fork of the codebase.

## 12. Known gaps before production

The foundation is intentionally fail-closed but is not yet production-complete. Required next controls include:

- tenant, membership, role and entitlement database schema
- PostgreSQL Row-Level Security
- authorization policy service
- cross-tenant denial integration tests
- audit event persistence
- rate limiting
- migration and rollback tooling
- encrypted backups and restore drills
- white-label domain verification
- Platform Health UI
- frontend migration away from localStorage authorization
- PlanAI service migration or explicit gateway integration

## 13. CI gate

Every pull request must pass:

- frontend production build
- Core API lint
- Core API tests
- module catalog JSON validation
- Docker Compose validation
- Core API container build

A red CI result is a blocked release, not a warning.
