# PLONAGRAM OS V1.7.5 — Agent-Ready Trace Gate Patch

This version does not add visual noise. It hardens engineering discipline.

## Adds

- Structured decision traces for every placed and unplaced SKU.
- Release gate test suite.
- Synthetic fixture cases.
- Engineering protocol docs.
- Release and security gates.
- Resource / Memory / Skill context map.

## Changed files

Backend:

- `backend/services/decision_trace.py`
- `backend/services/physical_capacity_engine.py`
- `backend/test_release_gate_v175.py`
- `backend/tests/fixtures/physics_cases_v175.json`

Docs:

- `AGENTS_PLONAGRAM.md`
- `docs/engineering-protocol.md`
- `docs/release-gates.md`
- `docs/security-gates.md`
- `docs/context-map.md`
- `docs/resources/fixture-catalog.md`
- `docs/memories/project-decisions.md`
- `docs/skills/physics-engine-review.md`

## Test

```bash
cd backend
python test_physics_engine_v174.py
python test_release_gate_v175.py
```

Expected:

```text
✅ V1.7.4 physics-first engine tests passed
✅ V1.7.5 release gate tests passed
```

## Rollback

Restore previous V1.7.4 files or remove:

- `backend/services/decision_trace.py`
- `backend/test_release_gate_v175.py`
- `backend/tests/fixtures/physics_cases_v175.json`

Then restore `backend/services/physical_capacity_engine.py` from V1.7.4.
