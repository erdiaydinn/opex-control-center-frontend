# EAY Roadmap 1–11 Acceptance

## Status

Roadmap items 1–10 remain cumulative prerequisites. Item 11 adds versioned Workforce demand and labor-standard authority without replacing the existing deterministic `demand_model.py` math kernel.

The controlling repository gate is **EAY Roadmap 1-11 Exact-Head Acceptance**. It must pass on the actual PR head SHA; a prior SHA or GitHub synthetic merge ref is not sufficient.

## Item 11 — Versioned demand → man-hour → required people

Repository/software acceptance requires:

- versioned, effective-dated labor standards;
- explicit source/provenance and approver identity;
- no guessed labor standard for non-zero demand;
- fail-closed behavior when effective authority is missing or ambiguous;
- deterministic `required_man_hours` for identical inputs, `model_version` and labor-standard versions;
- explainable contributor-level demand evidence;
- 15/30/60-minute demand intervals with deterministic required-people conversion;
- immutable input/output fingerprints;
- tenant-bound PostgreSQL persistence using canonical Workforce tenant authority;
- FORCE RLS, cross-tenant zero-read/zero-write and append-only labor-standard/demand evidence;
- idempotent exact replay of immutable standards and demand snapshots;
- cumulative exact-head re-proof of roadmap items 1–10.

## Truth boundary

`repository_software_acceptance=true` does **not** mean labor standards are field-calibrated or production-approved. Real customer demand feeds, measured task-time studies, data-owner approval, country/site calibration, staging load, field UAT and production sign-off remain external evidence requirements. No synthetic or sanitized fixture may be promoted as that evidence.

`production_ready=false` remains mandatory. Main merge and production activation remain forbidden from the category-leadership continuation.
