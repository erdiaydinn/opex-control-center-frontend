# EAY Repository Intelligence

The version-controlled registry at `config/repository_intelligence_registry.json` is the canonical session bootstrap for cross-repository knowledge. Ad-hoc chat memory is not authoritative when it conflicts with this registry.

## Invariants

- Every source is classified as `OWN`, `IMPORTED`, or `DISCOVERED`.
- Canonical seed entries cannot be silently removed; loader validation fails when any required seed disappears.
- An unresolved archive never receives a guessed `owner/repo`. Its repository identity remains `null`, the identity status remains `UNRESOLVED`, and its adoption decision remains pending until provenance is recovered.
- External code cannot be marked `ADOPT` unless its license has been explicitly verified.
- Canonical upstream/fork/derivative relationships are recorded independently from display names.
- Reviewed repository facts are pinned to branch/tag/ref plus commit SHA when the commit has actually been reviewed. Unknown SHAs remain `null` rather than being fabricated.
- Registry JSON is deterministically SHA-256 fingerprinted so downstream repository-memory snapshots can bind themselves to the exact registry state.

## Learning boundary

Repository learning preserves provenance at this granularity:

`repository -> upstream/fork relation -> branch/tag -> commit SHA -> file -> symbol/contract`

The registry layer provides the canonical source map, deterministic fingerprint, integrity gates, and a file-path admission filter. The filter excludes secret/private-key material and generated/vendor noise including `.env*`, private key containers, `node_modules`, `vendor`, build outputs, Python virtual environments, and caches.

Do not index raw secrets, credentials, tokens, generated dependency trees, or unnecessary personal data. Repository intelligence is retrieval/project memory, not an authorization source.

## Immutable review snapshots

`app/repository_review_snapshot.py` adds the temporal evidence layer above the registry. A review snapshot is an immutable manifest bound to:

- exact registry fingerprint,
- exact registry entry / repository identity,
- canonical upstream and relation,
- reviewed branch/tag/ref,
- exact 40-character commit SHA,
- review timestamp,
- one or more admitted file facts,
- file Git blob SHA,
- extracted symbol names and explicit contract statements,
- optional content SHA-256,
- prior snapshot fingerprint when the review continues an existing history.

The snapshot itself receives a deterministic SHA-256 fingerprint. A sequence of snapshots is hash-chained with `previous_snapshot_fingerprint`, so new reviews append history instead of replacing earlier project truth. Reordering, deletion of an interior review, field mutation, repository identity substitution, upstream substitution, registry-version substitution, duplicate paths, invalid Git/content hashes, unresolved identities, and excluded secret/generated paths fail closed.

## Append-only repository memory store

`app/repository_memory_store.py` persists verified snapshots as immutable JSON artifacts under a repository-entry directory and maintains a minimal append-only `index.jsonl` containing only fingerprint, commit SHA, and review timestamp.

Before every append, existing history is fully reloaded and hash-chain verified. A new snapshot must point to the exact current head fingerprint or the append fails. Duplicate snapshots, history forks, missing indexed artifacts, corrupt JSON, filename/index fingerprint substitution, reordered/deleted history, and tampered snapshot content fail closed.

Writes use a temporary file + `fsync` + atomic replacement for the snapshot artifact, followed by a separately `fsync`'d index append. If the index commit fails, the just-written unindexed snapshot is removed so partial history does not appear committed. JSON reload normalizes symbol/contract arrays back to immutable tuples before chain validation.

This filesystem store is local-first durable project memory. It is not WORM/tamper-proof storage against an operating-system or disk administrator; cryptographically signed external checkpoints are a future control if stronger evidentiary guarantees are required.

## Safe contract extraction

`app/repository_contract_extractor.py` performs deterministic structural extraction without retaining raw source text in repository facts:

- Python: function/class/constants, HTTP route method/path, and EAY/OPEX configuration variable names.
- SQL/DDL: `CREATE TABLE`, `CREATE VIEW`, and `ALTER TABLE` object contracts.
- YAML: workflow name, action identifiers, and presence of list-form or mapping-form run steps without shell-command contents.

Secret values are never copied into extracted contracts. Excluded paths are rejected before parsing, binary-like content fails closed, and invalid Python syntax is rejected rather than heuristically guessed.

## Read-only review ingestion coordinator

`app/repository_review_ingestion.py` composes already-fetched repository evidence into one verified memory transaction. Remote transport remains outside the trusted memory layer: the caller performs read-only GitHub retrieval and supplies the exact repository, ref, commit SHA, file path, blob SHA, and source text returned by that retrieval.

Before any snapshot is committed, the coordinator resolves the target through the canonical registry, rejects repository/ref/commit substitution, enforces exact Git blob identity and bounded file size, applies the secret/generated path gate, extracts only structural facts, stores content SHA-256 rather than raw source, reloads the existing append-only chain, and binds the new snapshot to the exact current head.

## GitHub object provenance adapter

`app/github_repository_evidence.py` verifies the remote object chain before project memory is touched:

`registry repository -> resolved ref -> commit SHA -> commit tree SHA -> tree path/blob SHA -> fetched UTF-8 source -> Git blob identity`

Repository/ref/commit/tree/blob substitution, paths absent from the commit tree, duplicate paths, invalid object hashes, and fetched source that does not reproduce the exact Git blob SHA fail closed. Git blob identity is recomputed using Git's canonical `blob <byte-length>\0<content>` object format; protocol SHA-1 is used only for Git object identity while EAY repository-memory manifests remain SHA-256 fingerprinted.

`ingest_verified_github_repository_review()` composes verified object evidence with the canonical registry, safe extractor, immutable review snapshot, and append-only local store. The adapter performs no network access, accepts no credentials, and cannot widen repository authority beyond the verified registry entry.

## Historical registry revisions

Historical truth is not reinterpreted under today's registry. `load_repository_registry_text()` applies the same schema, seed-preservation, identity, upstream, and license/adoption gates to an already-fetched historical registry JSON payload that the filesystem loader applies to the current registry.

`app/historical_repository_registry.py` then binds an old snapshot to that historical payload by requiring exact `snapshot.registry_fingerprint == historical_registry.fingerprint` before running the normal snapshot verifier. A modified/newer registry revision, a registry missing a canonical seed, or a snapshot invalid under its original source map fails closed. The caller must fetch the registry text from the immutable Git revision; no fallback to the current registry is permitted.

This means repository project memory now preserves both temporal axes: the reviewed repository commit and the exact source-registry revision that governed the review.

## External-source policy

External repositories are reference/adoption inputs, not architecture authority. Each reviewed external source records license status, capability mapping, reviewed ref/SHA, and one of `ADOPT`, `WATCH`, `REFERENCE`, `REJECT`, or `PENDING`.

Apache Superset is the canonical analytics upstream. `Patika-Global-Technology/superset-tr` is tracked only as a localization/vendor derivative and must not replace Apache Superset as upstream authority.

The supplied `council-of-high-intelligence-main.zip` archive is bound to verified upstream `0xNyk/council-of-high-intelligence`. Other supplied archives remain explicit unresolved entries until their exact upstream identities and license terms are recovered.

## Next layer

The next repository-intelligence slice should add optional signed checkpoint/export support so a local append-only chain can be independently anchored without claiming filesystem WORM guarantees. In parallel, continue exact upstream/license recovery for unresolved supplied archives and previously selected discovered repositories, never weakening registry completeness or commercial-license gates.
