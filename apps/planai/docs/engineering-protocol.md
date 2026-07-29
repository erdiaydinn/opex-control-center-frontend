# PLONAGRAM Engineering Protocol v1.7.5

This protocol applies to Plonagram and future OPEX modules.

## Operating rules

1. Prove the problem before patching.
2. Make assumptions visible.
3. Prefer small, reversible patches.
4. Build test fixtures before changing core logic.
5. No test, no release.
6. No speculative patch.
7. No unverified security claim.
8. UI and 3D are mirrors of backend state, not independent truth sources.
9. Every engine decision must have a structured trace.
10. Every unplaced SKU must have a reason code and human action.

## Patch template

- Problem
- Evidence
- Scope
- Changed files
- Not touched
- Tests
- Security impact
- Rollback
- Expected output
