# Legal instrument relationships

EAY models `amends`, `repeals`, and `supersedes` as separate reviewed evidence records instead of mutating legal status from a detected web change.

## Safety rules

- Self-references are rejected.
- The target instrument must already exist and cannot be draft.
- A proposed relationship starts as `pending`.
- Approval requires an explicit reviewer reference.
- Approval additionally requires the source instrument to be verified.
- Approval does not automatically change effective dates or mark the target as repealed/superseded.
- Relation evidence is fingerprinted with SHA-256 and duplicate proposals are idempotent; conflicting duplicate evidence fails closed.
- When an exact legal verification declares `amends`, `repeals`, or `supersedes`, successful instrument promotion and creation of the corresponding **pending** relation occur inside the same SQLite transaction. A relation conflict therefore rolls the instrument promotion and verification decision back together.
- The verification record stores the pending relation ID/fingerprint and the relation evidence reference binds it to the verification ID plus promotion-decision fingerprint.
- Relation staging never constitutes relation approval. The separate relation-review gate remains mandatory.

The transaction-aware relation helper deliberately avoids `sqlite3.executescript()` while a caller holds `BEGIN IMMEDIATE`; schema checks use individual statements so the caller's atomic boundary cannot be implicitly committed.

This separates three decisions that must not be conflated: whether a new instrument is authentic, whether it has a relationship to an older instrument, and when that relationship becomes legally effective.
