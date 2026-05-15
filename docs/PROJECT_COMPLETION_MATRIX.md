\# OPEX Project Completion Matrix



This document defines what "complete" means for each project/module in the OPEX Control Center ecosystem.



The goal is to prevent scope drift and keep all projects moving under one clear product umbrella.



\## Completion Philosophy



A project is not complete when it looks good.



A project is complete when:



\- Its purpose is clear.

\- Its users are clear.

\- Its route/module entry works.

\- Its data/source dependency is clear.

\- Its MVP scope is defined.

\- Its acceptance criteria are testable.

\- Its next phase is separated from current scope.

\- It can be explained to another developer or stakeholder without confusion.



\---



\## 1. OPEX Control Center Shell



\### Purpose



The main portal and operating layer for all OPEX modules.



\### MVP Scope



\- Home page

\- Module cards

\- Routing

\- Access Control entry

\- DockOS entry

\- Planogram entry

\- Budget entry

\- River redirect to DockOS

\- Basic build stability

\- GitHub repository discipline

\- Documentation foundation



\### Completion Criteria



\- / opens correctly.

\- /dockos opens correctly.

\- /access-control opens correctly.

\- /river redirects to /dockos.

\- /planogram opens correctly.

\- /budget opens correctly.

\- npm run build passes.

\- README, project registry, runbook and roadmap exist.

\- main and feature branch are synchronized when stable.



\### Current Status



Mostly complete for foundation phase.



\### Next Phase



\- Improve visual consistency.

\- Add clearer module status indicators.

\- Add production deployment planning.

\- Harden access control behavior.



\---



\## 2. DockOS



\### Purpose



DockOS is the operational module for dock, inbound, supplier reservation, PO/ST, shipment, plate search and exception workflows.



\### MVP Scope



\- DockOS route

\- Supplier reservation flow

\- Admin reservation review

\- Capacity management

\- PO/ST listing or lookup

\- Warehouse/date/status filtering

\- Plate number search

\- Required shipment detail field

\- Excel upload preview

\- Duplicate detection

\- Amount mismatch detection

\- Basic audit trail logic



\### Completion Criteria



\- DockOS opens from OPEX.

\- River redirects to DockOS.

\- Reservation flow works.

\- Admin review flow works.

\- Capacity screen works.

\- Plate search exists.

\- PO/ST search exists.

\- Excel upload does not mutate before preview.

\- Duplicate records are flagged.

\- Amount mismatch requires user decision.

\- Critical actions are auditable.

\- Build passes.



\### Current Status



Active development.



\### Next Phase



\- Backend-enforced permissions.

\- Supplier/vendor isolation.

\- Real data integration.

\- Accounting-friendly upload conflict flow.

\- Better operational dashboards.



\---



\## 3. Planogram Studio



\### Purpose



Planogram Studio is the darkstore layout, fixture, shelf, product placement and optimization intelligence module.



\### MVP Scope



\- OPEX /planogram route

\- Legacy PlanAI frontend bridge

\- PlanAI frontend on port 5174

\- PlanAI backend on port 8001

\- Basic Planogram UI opens

\- Fixture-first thinking documented

\- Constraint-first direction documented

\- Existing 2D/3D screens reachable



\### Completion Criteria



\- OPEX /planogram opens.

\- Legacy PlanAI frontend opens on 5174.

\- PlanAI backend runs on 8001.

\- No fatal console error.

\- Planogram UI is reachable from OPEX.

\- Local runbook explains service startup.

\- Known Three.js warnings are documented as non-fatal.



\### Current Status



Bridge working locally.



\### Next Phase



\- Stop treating 3D as the source of truth.

\- Build fixture model.

\- Build product dimension model.

\- Build constraint validation.

\- Add infeasible reason reporting.

\- Add solver/optimizer layer.

\- Eventually migrate legacy PlanAI into OPEX module structure.



\### Strategic Rule



Planogram is not complete until physical constraints are correct.



A beautiful 3D view with impossible shelf placement is a failed product.



\---



\## 4. Budget Intelligence



\### Purpose



Budget Intelligence is the OPEX finance and cost control module.



\### MVP Scope



\- Budget module route

\- Basic budget dashboard

\- Expense list

\- Store/category/supplier breakdown

\- Excel upload support

\- Duplicate detection

\- Amount mismatch review

\- Basic approval status

\- Export or reporting view



\### Completion Criteria



\- /budget opens.

\- User can view budget/expense records.

\- User can filter data.

\- Excel upload preview exists.

\- Duplicate records are flagged.

\- Amount mismatch is not overwritten silently.

\- Finance user can understand what action is required.

\- Build passes.



\### Current Status



Planned / entry exists.



\### Next Phase



\- Define data source.

\- Define upload format.

\- Define approval workflow.

\- Define finance audit trail.



\---



\## 5. Academy



\### Purpose



Academy is the learning, SOP, document, video and knowledge platform.



\### MVP Scope



\- Academy module entry

\- Light theme by default

\- Content library

\- Video/document listing

\- SOP pages

\- Role-based learning categories

\- Search

\- Basic progress/completion status



\### Completion Criteria



\- Academy opens.

\- Theme is light, calm and readable.

\- Users can browse learning content.

\- Users can open SOP/document/video content.

\- Content can be grouped by role or topic.

\- UI does not feel like a dark/cyber operations screen.



\### Current Status



Planned / design direction defined.



\### Next Phase



\- Upload flow.

\- Quiz flow.

\- RAG chatbot.

\- Source-grounded answers.

\- Ragas-style evaluation.



\---



\## 6. AI Insight Base



\### Purpose



AI Insight Base is the operational AI commentary and decision support layer.



\### MVP Scope



\- Define AI use cases

\- Define input datasets

\- Define output format

\- Define trace fields

\- Define human approval points

\- Define evaluation metrics

\- Start with one narrow use case



\### Possible First Use Cases



\- Daily OPEX commentary

\- NSFR / refund anomaly explanation

\- DockOS exception summary

\- Planogram recommendation explanation

\- Academy Q\&A over SOPs



\### Completion Criteria



\- AI output is traceable.

\- Input/output are stored.

\- Prompt version is known.

\- Retrieved sources are known when RAG is used.

\- Quality can be evaluated.

\- Human approval exists for critical actions.



\### Current Status



Planned.



\### Next Phase



\- LangGraph workflow design.

\- Langfuse trace design.

\- Ragas evaluation dataset.

\- First narrow AI workflow.



\---



\## 7. Access Control



\### Purpose



Access Control manages users, groups, modules and feature-level visibility.



\### MVP Scope



\- Access Control route

\- User/group permission structure

\- Module visibility logic

\- Protected route behavior

\- Super admin handling

\- Feature-level permission foundation



\### Completion Criteria



\- /access-control opens.

\- Protected routes do not crash.

\- Unauthorized users are redirected or warned.

\- Super admin behavior is clear.

\- Module cards can react to permission state.



\### Current Status



Foundation active.



\### Next Phase



\- Backend-enforced access control.

\- Full role matrix.

\- User management UI hardening.

\- Audit permission changes.



\---



\## Current Priority



1\. Finish project documentation foundation.

2\. Stabilize OPEX shell.

3\. Stabilize Planogram bridge.

4\. Stabilize DockOS MVP.

5\. Define Budget Intelligence MVP.

6\. Define Academy MVP.

7\. Define AI Insight Base first narrow use case.



\## What We Should Not Do Yet



\- Do not add more random UI features.

\- Do not expand AI features without eval/trace design.

\- Do not expand Planogram 3D before physical constraints are reliable.

\- Do not build Academy chatbot before content and permissions are clear.

\- Do not build Budget upload mutation before preview/conflict logic exists.



\## Decision



The immediate goal is not more features.



The immediate goal is:



\- Clear project boundaries

\- Clear MVP definition

\- Clear completion criteria

\- Clear next phase for each module

