# Backend Instructions

## Backend Philosophy

Backend is the source of truth for authorization, data filtering, business rules, validation, auditability, and safe integration with BigQuery or other systems.

Frontend must never be trusted for access control.

## API Design

Every endpoint should define:

- Input parameters
- Validation rules
- Response shape
- Error response
- Permission requirements
- Timeout behavior

## Security

Never expose broad operational data without role, vendor, warehouse, or permission filtering.

Supplier/vendor-facing endpoints must enforce data isolation in backend logic.

## BigQuery / Data Access

Be careful with:

- Europe/Istanbul timezone
- Date windows
- Large scans
- Timeout risk
- Dataset location mismatch
- Field name drift
- Null values
- Duplicate rows

Prefer query parameters, explicit limits, and clear error handling.

## Error Handling

Errors should include enough context for debugging but must not leak secrets.

Good error shape:

{
  "detail": "DockOS live purchase orders query timed out",
  "code": "BIGQUERY_TIMEOUT",
  "retryable": true
}

## Validation

For write endpoints:

- Validate required fields
- Validate enum values
- Validate ownership and permission
- Validate duplicates
- Validate amount mismatches
- Return actionable errors

## Audit

For operational mutations, store:

- user
- role
- timestamp
- before state
- after state
- reason
- source
