# Regulatory Change -> Legal Knowledge Review Workflow

EAY must never turn a webpage diff or model extraction directly into binding legal knowledge.

## State machine

`regulatory_change`
-> `pending_review`
-> `approved_for_verification`
-> `promoted_draft`
-> separate verified-instrument gate
-> eligible for binding legal requirements

A rejected candidate stops at `rejected`.

## Provenance rules

Every legal candidate stores an immutable copy of the detected regulatory diff plus its SHA-256 hash, source id/name/url/role and detection timestamp. Re-creating a candidate from the same regulatory change is idempotent.

A promoted instrument is always created with `verification_status=draft`. Promotion records the candidate id, regulatory change id and raw diff SHA-256 in provenance. It cannot become binding through the review endpoint.

## Why this matters

Discovery pages, ministry indexes and Resmi Gazete home-page changes are signals, not the legal text itself. The final verified instrument must still pass the Legal Instrument Engine verification rules before a normalized requirement may use `authority=legal`.

This prevents a local LLM, extraction heuristic or noisy webpage change from silently altering the company's legal baseline.

## API

- `POST /v1/legal/review/candidates`
- `GET /v1/legal/review/candidates`
- `POST /v1/legal/review/candidates/{id}/approve`
- `POST /v1/legal/review/candidates/{id}/reject`
- `POST /v1/legal/review/candidates/{id}/promote-draft`

The next phase will add authoritative instrument-document retrieval and a verification record containing exact source URL, publication metadata, content hash and reviewer evidence.