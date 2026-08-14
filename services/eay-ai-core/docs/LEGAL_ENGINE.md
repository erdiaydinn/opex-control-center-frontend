# EAY Legal Instrument Engine v0.1

## Purpose

The legal layer is deliberately separate from model weights. A model response is not a legal source. EAY stores authoritative legal instruments, effective dates and normalized requirements so answers can be evaluated against the law that was in force on a requested date.

## Trust model

A legal instrument can be stored as `draft`, but it can only be marked `verified` when:

- its source points to the official Resmî Gazete or Mevzuat Bilgi Sistemi domain;
- publication date is known;
- effective-from date is known.

A normalized `legal` requirement cannot be inserted unless its source instrument is verified. This prevents a Ministry news item, search result, model output or company document from being silently promoted into binding law.

Official Ministry/GKGM pages remain valuable for discovery and explanation. The Regulatory Watcher detects changes there, but detected changes remain pending review until the exact instrument is verified.

## Temporal model

Every instrument and normalized requirement can carry publication date, effective-from, effective-to and transition deadline metadata. Amendment/repeal/supersession links are stored separately as human-reviewed relation evidence.

`LegalTemporalResolver` resolves historical graph state for a requested `as_of` date. Its rules are deliberately conservative:

- only non-draft instruments with verified temporal metadata can participate;
- an approved relation becomes effective on the verified source instrument's `effective_from` date, so EAY does not invent a second independent relation date;
- `repeals` and `supersedes` deactivate their target on and after that date;
- `amends` records the relationship but does not deactivate the target by itself;
- relation cycles fail closed;
- multiple active superseders for the same target fail closed as ambiguous;
- missing publication/effective metadata fails closed;
- current `superseded`/`repealed` labels do not erase historical eligibility by themselves; historical resolution is driven by dated evidence and approved relations.

A successful resolution carries a deterministic SHA-256 `resolution_fingerprint`. If the graph is ambiguous, the API returns blockers instead of guessing which rule was in force.

All comparison queries accept an `as_of` date. This is required for questions such as "Was this compliant on 15 July 2026?" where today's rule may differ from the rule in force at that time.

## Company vs law conflict engine

Requirements are normalized into a small deterministic representation:

- `scope`: e.g. `chilled-storage`;
- `dimension`: e.g. `max_temperature_c`;
- `operator`: `<=`, `>=`, `==`, `required`, `prohibited`;
- value and unit;
- effective date range;
- source/citation.

The engine compares company requirements only against verified legal requirements with the same scope and dimension.

Possible outcomes:

- `company_stricter`: company rule is more conservative than the legal baseline;
- `aligned`: same requirement;
- `company_weaker_conflict`: company rule is weaker than or contradicts binding law;
- `incomparable`: units/operators/values cannot be safely compared automatically;
- `missing_legal_baseline`: company rule exists but no verified legal baseline is available for that scope/dimension/date.

`company_weaker_conflict` and `incomparable` require human review. EAY must not silently rewrite company policy or take irreversible compliance actions.

## API

- `POST /v1/legal/instruments` - insert/update an instrument.
- `GET /v1/legal/instruments?as_of=YYYY-MM-DD` - legacy date-window instrument view.
- `GET /v1/legal/temporal-state?as_of=YYYY-MM-DD` - fail-closed historical graph resolution with relation application and resolution fingerprint.
- `POST /v1/legal/requirements` - insert a normalized legal/company requirement.
- `GET /v1/legal/conflicts?as_of=YYYY-MM-DD` - deterministic company-vs-law comparison.

## Safety boundary

The temporal resolver is evidence resolution, not legal interpretation. It does not auto-approve relations, mutate instrument status, infer unstated revival rules, or promote watcher events into binding law. Ambiguity is surfaced for human legal review.
