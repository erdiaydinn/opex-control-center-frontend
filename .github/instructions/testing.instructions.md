# Testing Instructions

## Testing Philosophy

If it matters, it should be testable.

Testing includes:

- Unit tests
- API tests
- Integration tests
- UI tests
- Accessibility checks
- Manual verification checklist
- Regression checks

## Frontend Validation

Check:

- App builds
- Route loads
- Loading state
- Empty state
- Error state
- Success state
- Responsive behavior
- Keyboard navigation
- Accessible labels
- Role-based locators where possible

## Backend Validation

Check:

- Endpoint returns expected status
- Required params are validated
- Unauthorized requests fail
- Forbidden scoped data fails
- Empty data returns clean response
- Timeout is handled
- Bad input returns actionable error

## Playwright Guidance

Prefer:

- getByRole
- getByLabel
- getByText
- stable test IDs only when needed
- auto-waiting

Avoid brittle CSS selectors.

## API Test Cases

For every important endpoint, test:

- happy path
- missing parameter
- invalid parameter
- unauthorized
- forbidden
- empty result
- backend error

## Planogram Tests

Check:

- Product cannot exceed shelf width
- Temperature mismatch fails
- Mandatory SKU either placed or reported
- Infeasible reason is returned
- Renderer uses engine output

## DockOS Tests

Check:

- Supplier isolation
- Plate search
- PO/ST search
- Duplicate detection
- Amount mismatch conflict
- Excel preview before commit
- Audit creation after mutation

## RAG / AI Tests

Check:

- Faithfulness
- Source grounding
- Permission filtering
- No answer when source missing
- Prompt injection resistance
- Eval dataset score tracking
