# EAY Global Product Quality V3 Gate

## Authority

This document is a release-gate addendum to `EAY_PRODUCT_QUALITY_STANDARD.md`. It does not create a second quality framework. The human-readable standard and `config/product_quality_contract.json` remain the canonical EAY product-quality authority; CI enforces their machine-verifiable requirements.

Repository evidence proves repository quality only. It is not field, customer, staging-capacity or production acceptance evidence.

## Mandatory global inheritance

Every EAY product surface inherits the same platform-quality baseline:

- runtime locales: TR, EN, DE, AR, FR, ES, IT, NL, PL and PT-BR;
- Arabic uses structural RTL by changing the document direction, not by translating text alone;
- WCAG 2.2 AA is the minimum web release baseline;
- keyboard-only operation, visible focus and screen-reader semantics are required;
- reduced-motion and forced-colors operating-system preferences remain supported;
- text/reflow acceptance includes 200% scaling without loss of critical task functionality;
- mobile and terminal primary interaction targets remain at least 48dp;
- user-facing system state copy must be localized;
- offline behavior must be explicit rather than silently falling back to stale or demo truth.

## Five-state release matrix

A product surface is not release-eligible while any of these states is untracked:

`loading → error → empty → offline → retry`

The five-state matrix is mandatory for Control Center, Workforce, Hiring, Inventory, Planogram, DockOS, Budget, Academy, Jarvis, Insight/KPI and Field Intelligence. Domain-specific states such as partial, stale, conflict, rework or permission-denied remain additional requirements where applicable; they do not replace the global five-state baseline.

## Field Intelligence

Field Intelligence is now a first-class product-quality surface. Its critical quality flows are Mission Builder, targeting, capture, evidence, review, rework, reminder, escalation, verification and results. Real-device capture, barcode/camera behavior, policy-controlled GPS, offline synchronization, pilot-location acceptance and assistive-technology UAT remain external evidence gates.

Field evidence may enrich another EAY module only through governed promotion. A field submission is not automatically Inventory, Planogram, Finance or KPI authority.

## Release semantics

The global gate must fail closed when locale coverage, RTL behavior, accessibility bindings, required user states, accountable surface ownership or external-evidence declarations drift. Passing this gate does not set `production_ready=true`; it only proves that the repository continues to satisfy the EAY global product-quality contract at the tested SHA.
