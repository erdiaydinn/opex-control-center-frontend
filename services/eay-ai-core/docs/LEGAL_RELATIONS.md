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

This separates three decisions that must not be conflated: whether a new instrument is authentic, whether it has a relationship to an older instrument, and when that relationship becomes legally effective.
