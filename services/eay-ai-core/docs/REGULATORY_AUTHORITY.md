# Regulatory authority classification

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

## Current fixtures

Regression tests include the patterns currently seen on official Turkish food-regulation surfaces: GKGM public-consultation drafts, GKGM publication announcements, KAYSİS registry pages, the Resmî Gazete index, exact Resmî Gazete-like article text, and Ministry guidance. These fixtures test authority behavior rather than copying legal conclusions into model weights.
