# Plonagram Foundation Rebuild V1

This branch is the first controlled rebuild of PlanAI inside the OPEX repo.

## Canonical data flow

`catalog upload → normalization/enrichment → deterministic engine → strict validation → nested planogram → 2D/3D renderers`

There is one allocator: `POST /generate-planogram`. The `fast`, `lite` and
one-click routes are compatibility aliases and must return the same engine
semantics. Renderers are consumers; they do not invent shelves, products,
capacity, pallets or routes.

## What this foundation fixes

- Turkish export headers such as `Urun`, `Marka`, `Kategori`, `Storage`,
  `Derinlik` and `Onyuz` are normalized to canonical fields.
- Product-name detection uses token boundaries; `SuperFresh` is not treated as
  a water or shopping-bag product.
- Beverage multipacks receive a separate physical profile.
- Maximum default facing is breadth-first capped at five; physical fit can
  still reduce it further. The response exposes requested vs placed facing.
- Capacity, storage, weight, dimension, category and food/cleaning separation
  remain hard validation rules. Unplaced SKUs carry an explicit reason.
- 3D renders actual fixture, shelf and product data. It no longer draws fake
  product packages, hard-coded coolers, pallets, congestion markers or a fake
  route over every store.
- Layout editing validates bounds and object collisions before save.
- `allow_origins="*"` is removed. Configure `PLONAGRAM_ALLOWED_ORIGINS`.
- Login uses PBKDF2 hashes and signed bearer sessions. Audit and approval routes
  require roles; dimension requests are durable SQLite records.

## Security bootstrap

Set these before starting the backend:

```powershell
$env:PLONAGRAM_AUTH_REQUIRED = "true"
$env:PLONAGRAM_ENV = "development"
$env:PLONAGRAM_AUTH_SECRET = "replace-with-a-long-random-secret"
$env:PLONAGRAM_BOOTSTRAP_PASSWORD = "replace-with-a-12-character-password"
$env:PLONAGRAM_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
```

The bootstrap admin is created only when the user store is empty and an
explicit password is supplied. No `erdi/1234` account is created by source
code. Existing legacy hashes are upgraded after a successful login.

## Honest capacity behavior

The engine does not force all SKUs into shelves. A generated response should be
read with:

- `summary.capacity_by_storage`
- `summary.requested_facing_total`
- `summary.placed_facing_total`
- `summary.unplaced_reason_counts`
- `diagnostics.strict_rule_violations`

If CHILLED is at 95% and 14 products are unplaced, that is a cold-chain
capacity decision, not a successful plan. Add/resize the correct fixture or
change the assortment input, then regenerate.

## Current scope and next gates

This branch establishes the foundation. It does not claim final retail
optimization. The next gates are:

1. Validate master dimensions/images for the full SKU catalog; AI dimensions
   stay visibly marked as estimated.
2. Add a scenario/evaluation set for beverage, cold-chain, case-pack,
   brand-block and cleaning separation.
3. Add database-backed layout versioning and publish approval.
4. Replace local signed sessions with the company IdP/OIDC integration.
5. Add browser visual regression for the 2D editor and 3D scene.

