# EAY Legal Verification Chain

A regulatory signal or reviewed candidate is never enough to become binding legal knowledge.

Flow:

`watcher change -> review candidate -> draft instrument -> authoritative verification record -> verified instrument -> legal requirements/RAG`

## Verification evidence

A verification record stores:
- instrument id
- exact authoritative URL
- exact authoritative text snapshot
- SHA-256 content hash
- publication date
- effective date
- Official Gazette number when available
- decision and note
- timestamps

Only `resmigazete.gov.tr` and `mevzuat.gov.tr` sources can be used by this gate.

## Safety rules

1. Verification records start as `pending`.
2. A verification record can be decided only once.
3. Rejected records never change the legal instrument.
4. Only a verified record can promote a draft instrument to `verification_status=verified`.
5. Legal requirements still require a verified legal instrument.
6. The model may assist extraction, but cannot create a verified record or bypass these gates.
7. Stored content hashes make later provenance/tamper checks possible.

## API

- `POST /v1/legal/verification`
- `GET /v1/legal/verification`
- `POST /v1/legal/verification/{id}/verify`
- `POST /v1/legal/verification/{id}/reject`
