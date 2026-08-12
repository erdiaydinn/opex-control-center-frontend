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

Repository learning must preserve provenance at this granularity when available:

`repository -> upstream/fork relation -> branch/tag -> commit SHA -> file -> symbol/contract`

The first implementation provides the canonical registry, deterministic fingerprint, integrity gates, and a file-path admission filter. The filter excludes secret/private-key material and generated/vendor noise including `.env*`, private key containers, `node_modules`, `vendor`, build outputs, Python virtual environments, and caches.

Do not index raw secrets, credentials, tokens, generated dependency trees, or unnecessary personal data. Repository intelligence is retrieval/project memory, not an authorization source.

## External-source policy

External repositories are reference/adoption inputs, not architecture authority. Each reviewed external source records license status, capability mapping, reviewed ref/SHA, and one of `ADOPT`, `WATCH`, `REFERENCE`, `REJECT`, or `PENDING`.

Apache Superset is the canonical analytics upstream. `Patika-Global-Technology/superset-tr` is tracked only as a localization/vendor derivative and must not replace Apache Superset as upstream authority.

The supplied `council-of-high-intelligence-main.zip` archive is bound to verified upstream `0xNyk/council-of-high-intelligence`. Other supplied archives remain explicit unresolved entries until their exact upstream identities and license terms are recovered.

## Next layer

The next repository-intelligence slice should add immutable per-review snapshot manifests and symbol/contract extraction records bound to registry fingerprint + repository commit SHA. Any automated GitHub refresh must remain read-only by default and must never silently rewrite historical review truth.
