# OPEX Control Center — AI Working Constitution

## Product Context

OPEX Control Center is an operations intelligence platform. It is not just a dashboard.

Core modules may include:

- Planogram Studio
- DockOS
- Academy
- Budget / OPEX Finance
- AI Insight Base
- Operational KPI monitoring

The system must be built as a serious internal product: measurable, testable, secure, modular, and maintainable.

## Core Rule

Do not vibe-code.

Before changing code:

1. Understand the actual problem.
2. Read the relevant files.
3. Identify assumptions.
4. Propose the smallest safe change.
5. Preserve existing working behavior.
6. Validate with build, tests, or manual verification steps.
7. Explain risks and rollback if needed.

## Engineering Philosophy

Prefer:

- Small, atomic changes
- Clear domain language
- Explicit data contracts
- Testable functions
- Secure defaults
- Accessible UI
- Modular architecture
- Observable AI workflows

Avoid:

- Large blind rewrites
- Placeholder logic presented as complete
- UI polish that hides broken logic
- Direct mutation without understanding data flow
- Silent failures
- Hardcoded business rules without explanation
- Mixing legacy and new modules without boundaries

## AI System Philosophy

AI output is not enough.

Serious AI systems must be:

- Workflow-managed
- Validated
- Evaluated
- Observable
- Human-controlled at critical points

Reference architecture:

AI suggests.
LangGraph manages workflow.
OR-Tools validates and optimizes.
Ragas evaluates quality.
Langfuse traces and monitors.
Humans approve critical decisions.

## Planogram Principle

Planogram is a constraint problem before it is a visual problem.

Correct order:

1. Fixture model
2. Product dimensions
3. Business constraints
4. Physical capacity validation
5. Solver / optimizer
6. Infeasible reason report
7. Visual renderer

Never trust a beautiful visual if the physical model is wrong.

## DockOS Principle

DockOS handles operational execution and supplier/vendor-facing workflows.

Security and visibility rules must be designed first:

- A supplier must only see their own data.
- Warehouse and role-based access must be explicit.
- Duplicate, amount mismatch, PO/ST conflict, and manual override cases must be auditable.
- Excel uploads must be validated before mutation.

## Academy Principle

Academy must be clear, bright, accessible, and learning-oriented.

Default theme should be light and calm. Dark mode can exist as an option, not as the default.

If Academy uses RAG/chatbot:

- Answers must cite or ground themselves in source documents.
- The system must know which documents a user may access.
- Quality must be evaluated with test sets.
- Unsupported answers should admit uncertainty.

## UI Principle

Premium UI is not decoration.

Use animation and visual effects only when they improve:

- Orientation
- Focus
- Hierarchy
- Feedback
- Flow

Avoid heavy, distracting animation in operational screens.

## Security Principle

Assume users, prompts, files, and external content may be hostile.

Protect against:

- Prompt injection
- Secret leakage
- Unauthorized data access
- Overbroad API responses
- Unsafe file uploads
- Role bypass
- Cross-module visibility leaks

## Required Response Style for AI Assistants

When helping with this repo, prefer this structure:

1. What is likely wrong / needed
2. Files to inspect or change
3. Minimal implementation
4. Validation steps
5. Commit message

For complex work, use:

- Council lens
- Red-team critique
- Builder output
- Test plan

## Commit Discipline

Use clear commit messages:

- `fix: ...`
- `feat: ...`
- `refactor: ...`
- `test: ...`
- `docs: ...`
- `chore: ...`

Do not mix unrelated changes in one commit.
