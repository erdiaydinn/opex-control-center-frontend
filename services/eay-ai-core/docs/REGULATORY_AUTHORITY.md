# Regulatory authority classification and evidence lineage

EAY treats official Turkish regulatory web surfaces as evidence with different legal authority. Official origin alone does not make every page binding law.

## Authority classes

- `discovery_signal`: Ministry news, announcements and publication indexes. Useful for detecting change; never binding by itself.
- `official_nonbinding`: Draft legislation, consultation material, explanatory pages, guidance and guides.
- `official_registry`: Official registry/index entries that identify legislation but still require resolution to the exact legal instrument.
- `binding_candidate_unverified`: A Resmî Gazete-hosted document that looks like an exact legal instrument because it includes publication metadata and article structure. It is still not promoted automatically.

Every assessment has a deterministic SHA-256 fingerprint and always sets `auto_promotable_to_binding=false`.

## Mandatory promotion path

1. Discover or resolve the exact instrument.
2. Verify official source host and exact source text.
3. Verify publication date, effective date and any transition period.
4. Verify amendment/repeal/version relationships.
5. Human/legal review.
6. Only then create or update verified LEGAL knowledge.

A Ministry announcement that says a rule was published in the Resmî Gazete remains a discovery signal until the exact Resmî Gazete instrument is verified. A draft published for public consultation remains non-binding even when published on an official Ministry domain.

## Deterministic promotion gate

`app/legal_promotion_gate.py` evaluates exact-instrument candidates before a promotion workflow can proceed. It checks the authoritative host, exact-text SHA-256, publication/effective-date ordering, authority-assessment class, explicit human approval reference and amendment/repeal/supersession target requirements. Its output has a deterministic decision fingerprint.

Passing the gate means only `eligible_for_human_controlled_promotion`. The decision object hard-codes `auto_promote=false` and `requires_human_action=true`; no production legal knowledge or model weights are modified by this evaluator.

## Immutable watcher evidence lineage

`app/regulatory_lineage.py` adds an append-only SHA-256 chain for watcher evidence. Each lineage record stores the immutable record ID/type, source ID, content hash, canonical metadata, previous chain hash for the same source, deterministic chain hash and original timestamp.

The chain is source-scoped: activity on one official source cannot rewrite the provenance history of another source. Registering the exact same record twice is idempotent. Reusing an existing record ID with different content or metadata fails with `immutable_regulatory_lineage_conflict`.

`verify_source_chain()` recomputes the chain and reports the exact first broken record if historical evidence or a parent link has been altered. `import_existing_watcher_rows()` deterministically and idempotently backfills the existing `regulatory_snapshots` and `regulatory_changes` tables while preserving their original timestamps.

The lineage engine is intentionally separate from legal promotion. The current watcher tables can already be backfilled and verified; the next integration step is to write lineage records and authority-assessment fingerprints transactionally at watcher-change creation time.

A valid lineage proves what EAY observed and in which sequence; it does **not** prove that the observation is binding law. Authority classification, exact-instrument verification, effective-date/version resolution, promotion-gate eligibility and human approval remain independent gates.

## Current fixtures

Regression tests include GKGM public-consultation drafts, GKGM publication announcements, KAYSİS registry pages, the Resmî Gazete index, exact Resmî Gazete-like article text, Ministry guidance, immutable lineage conflict rejection, tamper detection, watcher-row backfill, content-hash mismatch, invalid temporal ordering, missing human approval and missing amendment/repeal targets. The CI suite verifies both compilation and these provenance invariants before changes are considered usable.
