# EAY AI Safety Gates

EAY keeps changing knowledge, actions and model weights behind separate gates.

## Regulatory knowledge

1. Watch authoritative source.
2. Store raw evidence and hash.
3. Human/legal review candidate.
4. Verify against Resmi Gazete / Mevzuat source.
5. Promote only verified instrument.
6. Index verified text with effective dates and provenance.

A watcher event never becomes binding law by itself.

## Company knowledge

Company policies are versioned independently from law. Only approved policy versions enter COMPANY retrieval. Historical `effective_from` / `effective_to` dates remain queryable.

## Data tools

The BigQuery path is fail closed:

- SELECT/WITH only.
- single statement only.
- dataset allow-list.
- bounded result rows.
- parameter dictionary carried separately from SQL.
- dry-run cost estimate before execution.
- maximum bytes billed policy.
- timeout policy.
- sensitive result-column masking.
- immutable execution audit identifier and SQL SHA-256.
- runtime execution disabled unless the deployment explicitly provides a trusted adapter.

Google BigQuery's official client supports dry-run queries, `maximum_bytes_billed`, job timeouts and query parameters; deployment integration should map the adapter contract to those controls.

## Visual audits

A visual model emits findings against a content hash, store, capture timestamp, model name/version and optional region. Findings begin as `pending`; they cannot become accepted operational evidence without a human decision. Re-running the same image/model/version combination is protected by an idempotency key.

## Training data

SFT candidates must be human approved. Examples containing personal data are rejected. Legal-claim examples require legal provenance metadata. Dataset bytes are canonicalized and SHA-256 hashed before a training run can reference them.

## Model release

New weights begin as `candidate`. Release approval is blocked unless regression, legal grounding, citation validity, unsafe-tool-call and KVKK leakage gates pass. Approval is a human action. Only an approved model can enter canary, and canary traffic is capped at 25% by the registry contract.

Production promotion is intentionally not automated in this version.
