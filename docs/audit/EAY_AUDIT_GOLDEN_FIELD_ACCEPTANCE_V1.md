# EAY Audit Golden Field Acceptance V1

## Purpose

This acceptance contract is derived from a real field audit supplied by the product owner and intentionally sanitized before entering the repository. No raw field images, employee identity, auditor identity, exact site identity or third-party report artifact is committed here.

The benchmark exists to prevent a technically strong vision model from producing operationally wrong audit truth.

## Non-negotiable field truths

### 1. Question text is not scoring authority

The same `YES` or `NO` answer can mean PASS or FAIL depending on the versioned standard.

Representative sanitized field patterns:

| Pattern | Expected | Failure |
| --- | --- | --- |
| prohibited condition present? | NO | YES |
| required clean condition satisfied? | YES | NO |
| waste overflow present? | NO | YES |
| emergency access available? | YES | NO |
| product directly on floor? | NO | YES |

Production programs therefore require a versioned `answer_semantics` contract. Natural-language polarity, Turkish negation or an LLM interpretation may never silently replace that contract.

### 2. Missing evidence is not N/A

`NOT_APPLICABLE` is valid only when the standard permits N/A and an applicability authority proves that the question does not apply, for example a governed Store DNA fact proving an asset is absent.

If an asset should be present but is not visible, if a camera angle misses it, or if a required employee/document/system observation was not collected, the result is `INSUFFICIENT_EVIDENCE` or `REVIEW_REQUIRED` rather than N/A.

### 3. Evidence modality is part of the standard

The field audit mixes several truth sources:

- VISUAL
- VIDEO
- DOCUMENT
- SYSTEM_DATA
- HUMAN_ATTESTATION
- OBSERVATION
- SENSOR

A question about employee knowledge cannot be answered authoritatively from a photo. A weekly inventory-control question should prefer authoritative Inventory system evidence where available. A training-completion question should prefer Academy/system truth. A visual cleanliness question may use privacy-verified image/video evidence.

### 4. Completion and score are separate

The report must expose at least:

- PASS
- FAIL
- NOT_APPLICABLE
- INSUFFICIENT_EVIDENCE
- REVIEW_REQUIRED
- completion state
- provisional score
- final score

N/A is excluded from the scoring denominator. Missing/review-required items block publication of a final score. An incomplete audit may show a provisional score but cannot present it as final truth.

### 5. Executive summaries are grounded artifacts

A field report supplied for this acceptance showed why free-form summary generation is unsafe: a generated summary can name the wrong site or describe a finding that contradicts the underlying answer.

EAY therefore builds the authoritative executive summary from exact run/location identity, score facts and finding IDs. Any optional narrative model is downstream commentary only and cannot replace the grounded artifact.

Every report fact must retain source references. Every finding must retain decision/evidence references.

### 6. Report media is privacy-verified only

Raw or client-claimed redacted media is never reportable evidence. PDF, email, thumbnails and shared report links may reference only evidence objects that passed the server privacy authority.

The report layer rejects a finding when its visible evidence set contains an unverified media reference.

### 7. Distribution is governed

Supported recipient classes are:

- user
- group
- location manager
- location contact
- explicitly authorized manual email

Manual email recipients require explicit authority. Raw media attachments are forbidden. Report delivery uses governed private links/artifacts and preserves an auditable recipient plan.

## Golden acceptance gate

Before a new Audit release candidate may be described as repository-ready for field truth, it must prove:

1. positive and negative question polarity cases resolve deterministically;
2. Turkish/question wording changes do not change scoring without a standards-version change;
3. missing visual evidence cannot become PASS or N/A;
4. N/A requires explicit applicability proof;
5. privacy-unverified media cannot enter a report;
6. incomplete audits cannot publish a final score;
7. report summary identity is bound to the exact audit snapshot;
8. report findings cannot be introduced without source references;
9. direct/manual recipients require explicit distribution authority;
10. field truth tests run on the exact PR head.

## Truth boundary

This benchmark proves repository semantics, scoring and report contracts. It does not claim that a live vision model, corporate mail provider, private report object store, mobile device fleet or field UAT environment is deployed. Those remain separate production evidence gates.
