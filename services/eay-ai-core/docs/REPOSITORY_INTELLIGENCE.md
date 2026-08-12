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

Historical snapshots intentionally remain tied to the exact registry fingerprint that existed when they were reviewed. Because the registry is version controlled, historical validation uses that registry revision rather than silently reinterpreting old evidence under a newer source map.

## External-source policy

External repositories are reference/adoption inputs, not architecture authority. Each reviewed external source records license status, capability mapping, reviewed ref/SHA, and one of `ADOPT`, `WATCH`, `REFERENCE`, `REJECT`, or `PENDING`.

Apache Superset is the canonical analytics upstream. `Patika-Global-Technology/superset-tr` is tracked only as a localization/vendor derivative and must not replace Apache Superset as upstream authority.

The supplied `council-of-high-intelligence-main.zip` archive is bound to verified upstream `0xNyk/council-of-high-intelligence`. Other supplied archives remain explicit unresolved entries until their exact upstream identities and license terms are recovered.

## Next layer

The next repository-intelligence slice should add read-only GitHub review ingestion that creates persisted snapshot artifacts from selected commits and extracts safe code/API/schema/SQL/CI/security contract facts without storing repository credentials or raw secret material. Snapshot persistence must be append-only and historical registry revisions must remain independently verifiable.
