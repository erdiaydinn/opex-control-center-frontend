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

Official-source evidence also has an append-only, source-scoped SHA-256 lineage chain (`app/regulatory_lineage.py`). Existing snapshot/change rows can be backfilled idempotently, and chain verification detects altered historical evidence or broken parent links. A valid chain proves observation history only; it never upgrades discovery, draft, guidance, registry or unverified instrument-candidate material into binding law.

## Company knowledge

Company policies are versioned independently from law. Only approved policy versions enter COMPANY retrieval. Historical `effective_from` / `effective_to` dates remain queryable.

## Data tools

The BigQuery path is fail closed:

- The model chooses a typed tool intent; it does not submit SQL to the execution bridge.
- Execution compiles an allow-listed `query_id` to a reviewed SQL template.
- Required scopes are checked before SQL compilation.
- Tool arguments use strict schemas (`extra=forbid`).
- Unsupported KPI semantics or catalog fields fail closed instead of silently returning a different metric.
- Every executable KPI is bound to a versioned semantic contract as well as a versioned schema contract. Semantic contracts explicitly pin numerator, denominator, unit, aggregation and precedence, and expose deterministic SHA-256 fingerprints.
- A KPI whose semantic contract is not reviewed cannot execute even when a plausible source table exists. NSFR/PFR/Refund semantic contracts are already pinned, including `PFR overrides Refund` and `Refund overrides Compensation`, but remain blocked until the production column mapping is independently verified.
- A reviewed KPI must also reference a reviewed schema contract. Immediately before KPI dry-run/execution, the adapter introspects the live BigQuery table and verifies the required column names/types against the contract.
- KPI schema contracts expose deterministic SHA-256 fingerprints over only the required columns. Additive unrelated columns do not break execution, while a missing required column or required-column type drift blocks the query before dry-run.
- If schema introspection is unavailable, KPI execution fails closed rather than trusting a stale contract.
- Successful KPI tool results return both semantic and schema verification fingerprints so the calculation meaning and data shape are auditable together.
- The execution audit persists semantic contract ID/fingerprint and schema contract ID/fingerprint alongside SQL SHA-256, cost limit, timeout, requester and reason. Existing SQLite audit databases are migrated additively; production actions remain reversible and provenance-preserving.
- Regulatory-impact callers provide only `instrument_id` + `as_of`; free-text impact topics are forbidden. The executor resolves search topics deterministically from the verified, effective instrument and its effective normalized legal requirements, then returns source/citation grounding with the result.
- Draft, superseded, expired, future-effective or topic-less legal evidence cannot drive a regulatory-impact catalog query.
- SELECT/WITH only, single statement only, dataset allow-list, and bounded result rows.
- BigQuery parameters remain separate from SQL; ARRAY parameters use the client library's array-parameter type.
- Dry-run cost estimate occurs before execution.
- Maximum bytes billed and timeout policies are enforced.
- Sensitive result-column masking is applied before rows leave the executor.
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
