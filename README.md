# OPEX Control Center Frontend

OPEX Control Center is a modular operations intelligence frontend workspace.

This repository contains the frontend layer for the OPEX Control Center initiative, including module routing, access control foundations, DockOS UI integration, Planogram Studio entry, Budget Intelligence entry, and AI working instructions for disciplined development.

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