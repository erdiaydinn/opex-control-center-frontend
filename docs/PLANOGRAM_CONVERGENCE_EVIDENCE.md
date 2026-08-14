# EAY Planogram Physical Truth Convergence Evidence

This document records repository-level physical-truth integration evidence only. It does **not** declare Planogram production-ready, authorize a merge to `main`, or substitute synthetic fixtures for real store/product measurements.

## Integration line

- Parent convergence: `release/platform-convergence-v0.1`
- Planogram child: `release/platform-convergence-planogram-v0.1`
- Deterministic foundation source: `agent/plonagram-foundation-clean-v1-20260729` @ `1609816c877d2b806ef145541288629da73f336e`
- Physical truth source: `agent/planogram-physical-truth-layer-v1` @ `bf7d026ee09bb1d46aa8a93daa77771bbd3754bb`

## Selective composition decisions

Only the minimum deterministic solver + physical-truth dependency graph was carried forward. The standalone PlanAI application shell was intentionally not imported.

Included:
- deterministic `engine.py` and `overrides.py`;
- Planogram backend dependency manifest;
- deterministic foundation regression tests;
- physical truth normalization, hard-constraint engine and audit CLI;
- physical truth, physical engine and audit tests.

Intentionally excluded:
- standalone `apps/planai/backend/main.py`;
- standalone `auth_routes.py` and `security.py`;
- separate `apps/planai/frontend`;
- historical 3D/UI migration surface;
- any replacement of the existing EAY `src/modules/planogram/PlanogramStudio.jsx` shell.

This preserves the current EAY platform identity/security authority and avoids introducing a competing PlanAI login/runtime.

## Repository evidence already observed

- selective source/provenance scope guard: PASS;
- 37 deterministic foundation + physical truth tests: PASS;
- physical truth surface compile: PASS;
- deliberately incomplete raw SKU master exits fail-closed with status 2: PASS;
- incomplete master keeps `production_ready=false` and `solver_optimizer_allowed=false`: PASS;
- missing approved dimensions remain a blocker: PASS;
- large beverage multipack fixture requirement remains PALLET: PASS;
- fully approved synthetic product/layout/Store DNA fixture opens the production gate in the canonical unit contract: PASS;
- missing pallet, estimated dimensions, invalid picker aisle width and unmeasured Store DNA remain blockers in canonical tests: PASS;
- repository hygiene `git diff --check`: PASS;
- one-shot write-capable selective-port workflow self-deleted and is absent from the resulting source commit.

## Cross-module convergence regressions closed during PR #79

PR merge-result validation exposed two pre-existing frontend acceptance drifts and one real Workforce importer defect. They were fixed without weakening the Planogram physical gate or restoring deprecated browser authority.

- The old access smoke still imported deleted `src/auth/accessConfig.js`. The smoke now explicitly asserts that this legacy browser-local grant authority remains absent, verifies the immutable server-derived authorization snapshot, forbids browser persistence, and checks canonical module-card coverage.
- Workforce XLSX `[h]:mm:ss` values above 24 hours were being materialized as `Date` objects and a 26-hour duration was incorrectly decoded as 3,000 minutes. XLSX parsing now preserves raw numeric duration serials while `dateToIso` explicitly decodes numeric Excel date serials. The canonical 26-hour fixture again resolves to 1,560 gross minutes without weakening >11-hour anomaly handling.
- The targeted Workforce importer fix passed `test:workforce-imports`, the full Workforce frontend contract suite, and the production frontend build before its one-shot write workflow self-deleted.

## Exact-head requirement

The Planogram child is not eligible to compose back into the parent until the same exact head passes the permanent read-only `EAY Planogram Physical Truth Convergence` gate and the PR merge-result cumulative gates, including Platform Core, DockOS/Workforce frontend and PostgreSQL acceptance, Academy convergence, canonical physical-truth tests, compile, raw-master fail-closed smoke, platform-authority boundary guard and the existing EAY shell production build.

## External production acceptance remains open

The physical gate is intentionally stronger than the currently available data. Real production acceptance still requires at minimum:
- authoritative SKU physical dimensions with approved provenance;
- product image/media coverage from an authoritative master;
- measured/user-approved Store DNA for real warehouses;
- real shelf/pallet/chiller/freezer fixture geometry and capacities;
- actual production catalog coverage rather than synthetic fixtures;
- warehouse scenario validation and operational acceptance.

Until these real inputs pass the gate, `production_ready` must remain false. No UI/3D polish should be treated as a substitute for this evidence.
