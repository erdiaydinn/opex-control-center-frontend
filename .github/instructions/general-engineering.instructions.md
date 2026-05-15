# General Engineering Instructions

## Default Workflow

Before implementing:

1. Restate the problem.
2. Inspect relevant files.
3. Identify affected modules.
4. Make the smallest safe change.
5. Preserve existing behavior unless explicitly changing it.
6. Validate.
7. Summarize what changed.

## Code Quality

Prefer:

- Named functions over giant inline blocks
- Clear error messages
- Explicit return shapes
- Defensive checks at boundaries
- Domain-specific naming
- Minimal dependencies

Avoid:

- Magic strings scattered across files
- Copy-pasted business logic
- Silent catch blocks
- Unused abstractions
- Over-engineering for imaginary future needs

## Architecture

Keep modules separated.

OPEX shell/auth/navigation/permissions should stay separate from module internals.

Planogram Studio, DockOS, Academy, and Budget should have clear module boundaries.

## Refactoring Rule

Never refactor and add features in the same change unless necessary.

If refactoring is required, explain why.

## Failure Handling

Errors should be visible, actionable, and traceable.

Bad:

"Something went wrong"

Good:

"DockOS PO fetch failed: BigQuery timeout after 60 seconds. Try narrower date range or refresh later."

## Acceptance Criteria

Do not use weak acceptance criteria like:

- "User can test manually"
- "Looks good"
- "Should work"

Use verifiable criteria:

- Build passes
- Endpoint returns expected status
- UI shows empty/loading/error/success states
- Role-based access works
- Existing route behavior is preserved
