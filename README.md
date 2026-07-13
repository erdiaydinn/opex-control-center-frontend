# OPEX Control Center

OPEX Control Center is a modular operations intelligence workspace. The repository now contains the React frontend and the DockOS RC7.5 FastAPI backend required for internal testing.

It includes module routing, access control foundations, DockOS UI and API integration, Planogram Studio entry, Budget Intelligence entry, and AI working instructions for disciplined development.

## DockOS RC7.5 Full Stack

- `src/modules/DockOS`: React user interface
- `backend/app/modules/dockos`: FastAPI routes, access enforcement, slot/reservation logic, audit and notification outbox
- `backend/app/main.py`: standalone API entry point
- `ops/dockos`: readiness and notification operation scripts
- `docker-compose.yml`: frontend + backend internal test stack

Copy `.env.example` to `.env`, replace every placeholder secret/address, then start the internal test stack:

```bash
docker compose up --build
```

Open `http://localhost:8080`. The API health endpoint is `http://localhost:8000/api/dockos/health`.

Windows internal test without Docker or administrator rights:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\INSTALL_DOCKOS_RC75_FULLSTACK.ps1
.\START_DOCKOS_RC75_FULLSTACK.ps1
.\TEST_DOCKOS_RC75_FULLSTACK.ps1
```

Do not use placeholder SMTP recipients or `CHANGE_ME` secrets outside local testing. The readiness endpoint must report `ready: true` before a live release.

## Branch Structure

main:
Stable / default branch.

feature/opex-command-center-v2:
Active development branch.

## Core Modules

- Control Center Home
- DockOS
- Planogram Studio
- Budget Intelligence
- Access Control
- Academy
- AI Insight Base

## Local Development

Install dependencies with:

npm install

Run development server with:

npm run dev

Default local URL:

http://localhost:5173/

Useful routes:

/
 /dockos
 /access-control
 /river
 /budget
 /planogram

The /river route currently redirects to /dockos.

## Build

Run production build with:

npm run build

A successful build should end with a "built in ..." message.

Backend validation:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\pip install -r requirements.txt
# Windows: .venv\Scripts\python -m app.modules.dockos.test_rc2
```

React Router or Framer Motion "use client was ignored" warnings may appear. These are non-fatal unless the build exits with an error.

## Development Discipline

Before committing changes:

1. Check current branch.
2. Review changed files.
3. Run build.
4. Commit with a clear message.
5. Push to the active feature branch.

Recommended workflow:

git status
npm run build
git add .
git commit -m "feat: short clear message"
git push

Avoid committing broken builds.

## AI Working Instructions

This repository includes AI working instructions under:

.github/copilot-instructions.md
.github/instructions/

Core principle:

Do not vibe-code.
Understand the problem.
Inspect relevant files.
Make the smallest safe change.
Validate with build/tests.
Commit only clean work.

## Product Principles

### OPEX Control Center

OPEX Control Center is not just a dashboard. It should evolve into an operational intelligence and execution platform.

### Planogram Studio

Planogram is a constraint problem before it is a visual problem.

Correct order:

Fixture model
Product dimensions
Business constraints
Physical capacity validation
Solver / optimizer
Infeasible reason report
Visual renderer

### DockOS

DockOS must prioritize:

- Role-based visibility
- Supplier/vendor isolation
- Auditability
- Excel upload validation before mutation
- Duplicate and amount mismatch handling
- Clear operational filtering

### Academy

Academy should be light, calm, accessible, and learning-oriented by default.

If AI/RAG features are added, answers must be grounded in accessible source documents and evaluated with quality metrics.

## Future AI Architecture

AI suggests.
LangGraph manages workflow.
OR-Tools validates and optimizes.
Ragas evaluates quality.
Langfuse traces and monitors.
Humans approve critical decisions.

## Security Notes

Do not commit:

- Real .env secrets
- API keys
- Service account JSON files
- Tokens
- Passwords
- Private credentials

Use .env.example for documented environment variables when needed.

## Maintainer

Owner: Erdi Aydın
