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

- The model chooses a typed tool intent; it does not submit SQL to the execution bridge.
- Execution compiles an allow-listed `query_id` to a reviewed SQL template.
- Required scopes are checked before SQL compilation.
- Tool arguments use strict schemas (`extra=forbid`).
- Unsupported KPI semantics or catalog fields fail closed instead of silently returning a different metric.
- Regulatory-impact callers provide only `instrument_id` + `as_of`; free-text impact topics are forbidden. The executor resolves search topics deterministically from the verified, effective instrument and its effective normalized legal requirements, then returns source/citation grounding with the result.
- Draft, superseded, expired, future-effective or topic-less legal evidence cannot drive a regulatory-impact catalog query.
- SELECT/WITH only, single statement only, dataset allow-list, and bounded result rows.
- BigQuery parameters remain separate from SQL; ARRAY parameters use the client library's array-parameter type.
- Dry-run cost estimate occurs before execution.
- Maximum bytes billed and timeout policies are enforced.
- Sensitive result-column masking is applied before rows leave the executor.
- Execution audit records preserve SQL SHA-256 without storing model-authored executable SQL.
- Runtime execution is disabled unless the deployment explicitly enables the trusted BigQuery adapter.

Google BigQuery's official Python client supports named scalar/array parameters, dry-run queries, `maximum_bytes_billed` and `job_timeout_ms`; the EAY adapter maps the template contract to those controls.

## Visual audits

A visual model emits findings against an image content hash, store, capture timestamp, model name/version and optional region. Findings begin as `pending`; they cannot become accepted operational evidence without a human decision. Re-running the same image/model/version combination is protected by an idempotency key.

A separate visual-provenance record hashes the source URI, image hash, model identity and findings hash into an evidence-chain SHA-256. Pending audits are exposed through a human-review queue. Visual examples are eligible for learning only when the audit is accepted **and** provenance has been registered.

## Training data

SFT candidates must be human approved. Examples containing personal data are rejected. Legal-claim examples require legal provenance metadata. Dataset bytes are canonicalized and SHA-256 hashed before a training run can reference them.

Accepted datasets can be registered as immutable training manifests. Each manifest records dataset SHA-256, reviewer/approval reference, parent manifest and a chain SHA-256. This creates explicit lineage between training dataset versions and prevents an unreviewed dataset from silently replacing an approved one.

## Model release

New weights begin as `candidate`. Release approval is blocked unless regression, legal grounding, citation validity, unsafe-tool-call and KVKK leakage gates pass. Approval is a human action. Only an approved model can enter canary, and canary traffic is capped at 25% by the registry contract.

The release gate additionally requires a RAG evaluation sample set with >=99% pass rate, 100% effective-date validity, 100% legal-source grounding for legal cases, and zero duplicate evidence. A model cannot be promoted merely because runtime canary metrics look healthy while retrieval correctness has regressed.

Production promotion is intentionally not automated in this version.
