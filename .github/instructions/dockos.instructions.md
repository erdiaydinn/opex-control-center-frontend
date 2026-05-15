# DockOS Instructions

## Product Role

DockOS is an operational control module for inbound, supplier, PO/ST, shipment, receiving, and exception workflows.

It should reduce manual searching, supplier confusion, duplicate entry, and accounting friction.

## Core Principles

- Role-based visibility first
- Supplier/vendor isolation first
- Auditability first
- Excel upload validation before mutation
- Clear exception handling
- Fast filtering and search

## Required UX States

DockOS screens should support:

- Search by supplier
- Search by plate number
- Search by PO/ST/reference
- Warehouse filter
- Date filter
- Status filter
- Required shipment details
- Info tooltip explaining what to enter

## Excel Upload Rules

When Excel upload is supported:

1. Parse file.
2. Validate columns.
3. Normalize supplier, PO/ST, amount, date.
4. Detect duplicates.
5. Detect amount mismatch.
6. Ask which record is valid when conflict exists.
7. Preview before committing.
8. Store audit trail.

## Duplicate Logic

Duplicates should not be blindly overwritten.

Cases:

- Same reference, same amount: likely duplicate.
- Same reference, different amount: conflict.
- Same supplier/date/amount but different reference: suspicious.
- Missing reference: requires manual review.

## Security

Never rely on frontend filters for supplier visibility.

Backend must enforce:

- supplier ownership
- warehouse access
- role permissions
- action permission

## Performance

Large operational queries should support:

- Date limits
- Pagination
- Search parameters
- Timeout handling
- Backend caching where safe
