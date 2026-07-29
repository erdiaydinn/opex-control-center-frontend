# Project Decisions

- OPEX route `/planogram` stays at `localhost:5173/planogram` and shows legacy PlanAI at `localhost:5174` via iframe bridge during migration.
- Store DNA is the source of truth.
- Embedded catalog is system responsibility; stores upload ABC/sales reports, not catalog.
- Physics-first engine is mandatory before 3D polish.
- 3D is a state mirror, not a separate placement engine.
