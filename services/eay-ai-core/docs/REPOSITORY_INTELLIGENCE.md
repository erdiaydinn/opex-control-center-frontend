# EAY Repository Intelligence

The version-controlled registry at `config/repository_intelligence_registry.json` is the canonical bootstrap for cross-repository knowledge. Ad-hoc chat memory is not authoritative when it conflicts with the registry or exact GitHub evidence.

## Canonical authority

The active release authority is the current Pydantic registry/provenance model:

- `app/repository_intelligence.py` validates source identity, classification, license/commercial-use state, canonical upstreams, required seed coverage, deterministic registry fingerprints, and safe repository-learning paths.
- `app/repository_provenance.py` binds repository facts to the canonical registry, exact ref + commit SHA, file path, symbol/contract, content SHA-256, observation time, and temporal supersession.
- `config/repository_intelligence_registry.json` is cumulative and cannot silently drop required OWN / IMPORTED / DISCOVERED seed entries.
- `config/repository_archive_provenance.json` stores independently reviewed supplied-archive evidence where an exact archive-to-upstream tree match has been established.

Repository Intelligence remains read-only project knowledge. It is not Jarvis execution authority, an authentication source, a production-policy mutator, or a model-promotion path.

## Invariants

- Every source is classified as `OWN`, `IMPORTED`, or `DISCOVERED`.
- Unknown identities remain `pending` with blocked commercial use; owner/repo identities are never guessed.
- External adoption requires explicit license review. Copyleft references do not become proprietary EAY adoption authority merely because their upstream identity is verified.
- Canonical upstream and derivative relationships are explicit. Apache Superset remains the canonical analytics upstream; `Patika-Global-Technology/superset-tr` remains a localization/vendor reference.
- Reviewed facts are pinned to exact repository identity, ref and commit SHA when those values are reviewed.
- Registry and provenance fingerprints are deterministic SHA-256 values.
- Secrets, private-key material, generated dependency trees, build outputs and vendor noise are excluded from repository learning.

## Safe structural extraction

`app/repository_contract_extractor.py` is the only new extraction helper promoted by this convergence branch. It records structural facts without retaining secret values:

- Python: functions/classes/constants, HTTP method/path contracts and EAY/OPEX configuration variable names.
- SQL/DDL: `CREATE TABLE`, `CREATE VIEW` and `ALTER TABLE` object contracts.
- YAML: workflow name, action identifiers and the presence of run steps without persisting shell-command content.

Excluded paths are rejected before parsing, binary-like input fails closed, and invalid Python syntax is rejected instead of heuristically guessed.

## Supplied archive provenance

The archive provenance ledger currently records exact recomputed Git-tree matches for:

- `council-of-high-intelligence-main.zip` -> `0xNyk/council-of-high-intelligence` @ `c4d91f07c96e8bc36e3872bbf378ebd4e3f0ac72`, MIT, decision `watch`.
- `CL4R1T4S-main.zip` -> `elder-plinius/CL4R1T4S` @ `1a55b8a36d47c86e8d774acef83306d56fb0b302`, AGPL-3.0, decision `reference` and proprietary-EAY use restricted to reference-only.
- `computer-lab-automation-master.zip` -> `mustafadalga/computer-lab-automation` @ `0f6fa81448062488f01144c67032764af25ee5fe`, GPL-3.0, decision `reference` unless separately cleared.

The CI gate requires the registry identity/ref/commit/license/decision to agree with this ledger and rejects adoption drift.

Still unresolved supplied sources remain explicit `pending` entries, including Deep-Learning-Tutorials, impeccable, image_understanding and the supplied JARVIS archive family until exact provenance is recovered.

## Historical #39 capability

Historical Repository Intelligence PR/branch work includes an append-only review-memory store, signed Ed25519 external checkpoints, GitHub ref->commit->tree->blob verification and historical-registry replay. Those capabilities remain preserved in their historical branch/PR record.

They are **not** copied wholesale into the cumulative release branch because that implementation used a parallel registry/snapshot API that conflicts with the newer canonical Pydantic registry/provenance authority already present in Platform Convergence. Reintroducing the old API would be a regression.

If append-only persistence or signed checkpoints are promoted later, they must be reimplemented as consumers of the current `RepositoryRegistry` / `RepositoryFact` / `RepositorySnapshot` contracts and must pass full AI Core regression before convergence.

## Release gate

`.github/workflows/repository-intelligence-convergence.yml` verifies:

1. canonical registry tests,
2. current `repository_provenance.py` tests,
3. supplied archive provenance/license boundaries,
4. safe structural extraction,
5. full EAY AI Core regression,
6. preservation of modern Jarvis and model-training/promotion authority,
7. absence of the legacy parallel snapshot/memory authority from the cumulative branch.

No Repository Intelligence change is considered converged while any of those checks are red.

## Next work

Highest-value next Repository Intelligence work is provenance debt closure, not new architecture:

1. recover exact upstream/ref/SHA/license for unresolved supplied archives,
2. recover previously selected discovered repositories by capability domain,
3. review commercial-use obligations before any adoption decision,
4. generate current-model provenance facts for the highest-value verified sources,
5. only then consider a current-model append-only persistence/checkpoint layer if it materially improves release or audit acceptance.
