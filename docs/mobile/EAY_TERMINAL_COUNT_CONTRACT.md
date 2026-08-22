# EAY Terminal — Blind Count Contract v1

## Non-negotiable behavior

A field count is blind. The execution model contains no expected-stock quantity and does not accept one as an input. Expected/system stock belongs to the governed server reconciliation phase after field evidence exists.

## Scanner boundary

Terminal count defaults to hardware DataWedge input. Camera/manual entry can exist only when a mission/server/device policy explicitly permits that source. Scan ingress validates source event id, source type, symbology, payload size, control characters and timestamp freshness before the payload enters a mission flow.

Trailing CR/LF appended by scanner profiles may be normalized. GS1 group separators remain valid. Raw barcode values are operational data and are forbidden from routine telemetry; Mobile Core uses a SHA-256 payload hash for correlation/proof contracts.

Reusing a scanner source-event id with a changed payload is substitution, not a harmless duplicate.

## Count state machine

`SCAN_LOCATION -> SCAN_ITEM -> ENTER_QUANTITY -> CONFIRM_ITEM -> ... -> COMPLETE`

- Physical location must be scanned and match the mission location token before item work starts.
- Quantity cannot be entered before a valid item scan.
- Quantity is bounded and explicit zero is allowed for a genuine observed zero.
- Confirm emits field evidence containing mission id, item payload hash and observed quantity.
- A bounded target cannot silently accept additional lines.
- Unexpected SKU classification, product metadata and reconciliation remain server-governed later stages; they must not leak expected stock into the blind field state.

## Next implementation boundary

The proven Inventory DataWedge adapter will be wired into this Scanner ingress contract, then count-line evidence will be serialized into the common Mobile Event Ledger and encrypted Sync queue. That adapter step must preserve the existing physical scanner behavior and requires device-matrix acceptance before production truth.
