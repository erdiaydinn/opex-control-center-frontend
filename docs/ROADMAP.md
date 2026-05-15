\# OPEX Control Center Roadmap



This roadmap defines the staged development plan for the OPEX Control Center ecosystem.



The goal is not to build disconnected tools. The goal is to build a modular operations intelligence and execution platform.



\## Product Vision



OPEX Control Center should become the central workspace for:



\- Operational visibility

\- Execution control

\- Planning intelligence

\- Training and knowledge management

\- AI-assisted decision support

\- Role-based access and governance



Core principle:



Build a serious internal product, not a collection of demos.



\---



\## Phase 0 — Foundation



Status: Mostly completed.



Purpose:



Establish the engineering, repository, and documentation foundation.



Completed:



\- GitHub repository created.

\- main branch configured as default.

\- feature/opex-command-center-v2 pushed.

\- README added.

\- AI working instructions added.

\- Project registry added.

\- Local runbook added.

\- DockOS permission handling added.

\- Build validated.



Key files:



\- README.md

\- docs/PROJECT\_REGISTRY.md

\- docs/LOCAL\_RUNBOOK.md

\- .github/copilot-instructions.md

\- .github/instructions/



Next improvements:



\- Add architecture document.

\- Add ports and services document if needed.

\- Add issue templates later.

\- Add pull request template later.



\---



\## Phase 1 — OPEX Shell



Status: Active.



Purpose:



Stabilize the OPEX Control Center shell as the main portal.



Scope:



\- Home page

\- Module cards

\- Routing

\- Access control

\- Protected routes

\- Module visibility

\- Navigation consistency

\- Main/default branch hygiene



Key routes:



\- /

\- /dockos

\- /planogram

\- /budget

\- /access-control

\- /river



Expected behavior:



\- / opens the OPEX home.

\- /dockos opens DockOS.

\- /access-control opens access management.

\- /river redirects to /dockos.

\- /planogram opens Planogram Studio integration.

\- Module cards should respect user permissions.



Acceptance criteria:



\- npm run build passes.

\- Routes load without white screen.

\- Permission behavior is predictable.

\- No broken navigation.

\- No critical console errors.



\---



\## Phase 2 — DockOS



Status: Active development.



Purpose:



Build DockOS as the operational dock, inbound, supplier reservation, PO/ST, shipment and exception management module.



Core priorities:



1\. Supplier/vendor isolation

2\. Role-based visibility

3\. Warehouse filtering

4\. PO/ST search

5\. Plate number search

6\. Required shipment details

7\. Excel upload flow

8\. Duplicate detection

9\. Amount mismatch handling

10\. Audit trail



Important workflows:



\- Supplier reservation creation

\- Admin reservation review

\- Capacity management

\- PO/ST lookup

\- Shipment detail validation

\- Excel upload preview

\- Conflict resolution before mutation



Excel upload logic:



\- Parse file.

\- Validate columns.

\- Normalize supplier, PO/ST, date and amount.

\- Detect duplicates.

\- Detect amount mismatch.

\- Ask which record is valid if conflict exists.

\- Preview before commit.

\- Store audit trail.



Acceptance criteria:



\- Supplier cannot see another supplier's data.

\- User cannot access unauthorized warehouse data.

\- Duplicate records are flagged.

\- Amount mismatch records require review.

\- Excel upload never mutates data before preview.

\- UI has loading, empty, error and success states.



\---



\## Phase 3 — Planogram Studio



Status: Legacy bridge active.



Purpose:



Build Planogram Studio as the physical layout, fixture, product placement and optimization intelligence module.



Current architecture:



\- OPEX frontend runs on port 5173.

\- Legacy PlanAI frontend runs on port 5174.

\- PlanAI backend runs on port 8001.

\- OPEX /planogram route points to the Planogram experience.



Current local services:



\- OPEX frontend: http://localhost:5173

\- Legacy PlanAI frontend: http://localhost:5174

\- PlanAI backend: http://127.0.0.1:8001



Core principle:



Planogram is a physical and mathematical constraint problem before it is a visual problem.



Correct order:



1\. Fixture model

2\. Product dimensions

3\. Business constraints

4\. Physical capacity validation

5\. Solver / optimizer

6\. Infeasible reason report

7\. Visual renderer



Near-term priorities:



\- Stabilize legacy iframe/integration.

\- Make port expectations explicit.

\- Clean non-fatal Three.js warnings later.

\- Confirm /bootstrap/ANKA works through backend 8001.

\- Keep Planogram accessible from OPEX portal.



Mid-term priorities:



\- Build fixture-first data model.

\- Model shelves, cold cabinets, frozen cabinets, Algida freezers, fruit and vegetable racks, pallets, walls and columns.

\- Add product dimensions, category, temperature requirement, sales velocity and facing rules.

\- Add infeasible reason reporting.

\- Introduce OR-Tools style optimization.



Future migration:



Move PlanAI frontend components into:



frontend/src/modules/planogram



Move PlanAI backend engine into:



backend/app/modules/planogram



Acceptance criteria:



\- Visual renderer does not invent placement.

\- Every placement comes from validated engine output.

\- Product cannot exceed fixture capacity.

\- Temperature mismatch fails.

\- Mandatory SKUs are placed or reported.

\- Infeasible results explain why.



\---



\## Phase 4 — Budget Intelligence



Status: Planned / early entry.



Purpose:



Build the OPEX finance and budget intelligence module.



Core priorities:



\- Expense tracking

\- Budget variance

\- Duplicate invoice / request control

\- Amount mismatch control

\- Store / supplier / category breakdown

\- Finance-friendly review workflow

\- Excel upload support

\- Approval and audit flow



Key principles:



\- Finance users should move fast without losing control.

\- Duplicate and mismatch cases should not be silently overwritten.

\- Uploaded Excel data should be previewed before mutation.

\- Every financial mutation should be auditable.



Acceptance criteria:



\- Budget data can be filtered clearly.

\- Duplicate records are flagged.

\- Amount mismatches require user decision.

\- Upload preview exists before commit.

\- Audit trail exists for important changes.



\---



\## Phase 5 — Academy



Status: Planned.



Purpose:



Build the internal learning, SOP, document, video and AI-assisted knowledge platform.



Theme principle:



Academy should be light, calm, accessible and learning-oriented by default.



Dark mode can exist as an option, but it should not be the default.



Core priorities:



\- Content library

\- Video/document upload

\- SOP pages

\- Role-based learning paths

\- Completion tracking

\- Quizzes

\- Search

\- AI chatbot later



AI/RAG principles:



\- Answers must be grounded in accessible documents.

\- The chatbot must respect user permissions.

\- Unsupported answers should admit uncertainty.

\- Quality should be evaluated with Ragas-style metrics.



Possible evaluation metrics:



\- Faithfulness

\- Answer relevancy

\- Answer correctness

\- Context precision

\- Context recall

\- Noise sensitivity

\- Factual correctness

\- Rubric-based evaluation



Acceptance criteria:



\- Users can find training content easily.

\- Content is role-based where needed.

\- UI is readable and calm.

\- AI answers cite or reference source material when possible.

\- AI does not invent company policy.



\---



\## Phase 6 — AI Insight Base



Status: Planned.



Purpose:



Build the AI-assisted operational commentary and decision support layer.



This should not be a simple chatbot. It should be a measurable, observable and controlled AI workflow layer.



Architecture principle:



AI suggests.

LangGraph manages workflow.

OR-Tools validates and optimizes.

Ragas evaluates quality.

Langfuse traces and monitors.

Humans approve critical decisions.



Possible use cases:



\- Daily operational commentary

\- Store anomaly explanation

\- NSFR / refund / PFR insight generation

\- Prep time and picking performance commentary

\- Supplier/category chronic issue detection

\- Planogram recommendations

\- DockOS exception summaries

\- Academy question answering



Workflow model:



State -> Node -> Decision -> Tool -> Validation -> Human Check -> Output



Required observability:



\- run\_id

\- user

\- module

\- session

\- prompt\_version

\- input

\- retrieved sources

\- output

\- model

\- latency

\- cost

\- error

\- quality score



Acceptance criteria:



\- AI output is traceable.

\- AI output is grounded where required.

\- Critical actions require human approval.

\- Evaluation datasets exist for important workflows.

\- Prompt/retriever/model changes are measured, not guessed.



\---



\## Phase 7 — Production Readiness



Status: Future.



Purpose:



Prepare the ecosystem for company/server deployment.



Core topics:



\- Domain strategy

\- Authentication

\- Authorization

\- Backend deployment

\- Frontend deployment

\- Environment variables

\- Secrets management

\- CI/CD

\- Logging

\- Monitoring

\- Error tracking

\- Backup and rollback

\- Access review

\- Security review



Deployment questions:



\- Where will the frontend be hosted?

\- Where will backend services run?

\- Which domain/subdomain will be used?

\- How will authentication work?

\- How will role permissions be managed?

\- Where will secrets be stored?

\- How will BigQuery credentials be handled?

\- How will logs and errors be monitored?



Acceptance criteria:



\- No local-only assumptions.

\- Environment variables documented.

\- Secrets are not committed.

\- Build pipeline works.

\- Rollback plan exists.

\- Access control is enforced on backend.



\---



\## Cross-Project Rules



Every major module must document:



\- Purpose

\- Current status

\- Local path

\- Local route

\- Port dependency

\- Git status

\- Known issues

\- Next action

\- Acceptance criteria



Do not add large features without:



\- Reading relevant files

\- Defining the problem

\- Making a small plan

\- Running build

\- Checking permissions

\- Considering rollback



\## Current Priority Order



1\. Keep repository and documentation clean.

2\. Stabilize OPEX shell and routing.

3\. Stabilize DockOS permission and visibility logic.

4\. Stabilize Planogram legacy bridge.

5\. Define Planogram fixture/constraint model.

6\. Add Budget Intelligence structure.

7\. Design Academy light-theme information architecture.

8\. Build AI Insight Base only after data/eval/trace strategy is clear.



\## Current Known Risks



\- Multiple local services can cause port confusion.

\- Planogram currently depends on legacy PlanAI frontend.

\- PlanAI frontend expects backend on port 8001.

\- Frontend visibility is not enough for security.

\- AI features can become unreliable if not evaluated.

\- 3D visuals can hide broken physical logic if solver/constraints are weak.

\- Too many modules can cause scope drift without roadmap discipline.



\## Immediate Next Actions



1\. Keep docs updated.

2\. Confirm OPEX routes manually.

3\. Confirm Planogram bridge works with 5173 + 5174 + 8001.

4\. Review DockOS permission behavior.

5\. Create ARCHITECTURE.md.

6\. Create PORTS\_AND\_SERVICES.md if needed.

7\. Start issue/task breakdown for DockOS and Planogram.

