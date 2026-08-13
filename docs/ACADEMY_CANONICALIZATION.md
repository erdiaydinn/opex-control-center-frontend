# EAY Academy canonicalization

## Canonical topology

- Historical branch: `product/academy-foundation-v1`.
- Historical parent: Workforce Experience PR #58 head `99bc25c4a6abe3fdcba28271fae7cfb0e1ddf437`.
- Historical Academy head: `f0a96638384815010286de0136fc6738115f21fd`.
- Historical delta: 12 Academy-only commits and 10 Academy/module files.
- Functional Workforce dependency: **none**; no Workforce import is required.
- Canonical base: Platform Security/Core PR #16 head `6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d`.
- Canonical branch: `product/academy-canonical-v1`.

The historical branch is retained as evidence and must not be force-rewritten or deleted. The canonical branch ports the Academy domain onto Platform Core and adds production persistence, APIs, media authorization, grounded SOP retrieval, migrations, tests and operational contracts.

## Preserved invariants

Entitlement, request-fingerprint idempotency, append-only learning audit, immutable content-version pinning, resumable progress, server-side quiz grading and completion/certificate contracts are preserved and strengthened.

## Workforce boundary

The Workforce Employee Center training tile is only a consumer integration surface. It is not Academy source-of-truth and remains a follow-up API integration; its prior local `%72 → %100` demo state cannot be counted as Academy completion.
