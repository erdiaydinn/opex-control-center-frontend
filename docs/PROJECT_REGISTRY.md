\# OPEX Project Registry



This document keeps the full project map for the OPEX Control Center ecosystem.



\## Main Platform



\### OPEX Control Center



OPEX Control Center is the umbrella platform for operational intelligence, execution, planning, learning, and AI-assisted decision support.



Local path:



C:\\Users\\ErdiAydın\\opex-control-center-scaffold\\frontend



GitHub repository:



https://github.com/erdiaydinn/opex-control-center-frontend



Branches:



main  

Stable / default branch.



feature/opex-command-center-v2  

Active development branch.



Local frontend port:



5173



Current status:



\- GitHub repo created.

\- main branch configured as default.

\- feature branch pushed.

\- AI working instructions added.

\- DockOS permission handling added.

\- README added.

\- Build passes.



\## Modules



\### 1. Control Center Home



Purpose:



Main landing page for OPEX modules.



Status:



Active.



Notes:



Should act as the entry point for all modules and show module cards based on access rights.



\---



\### 2. DockOS



Purpose:



Operational dock, inbound, supplier reservation, PO/ST, shipment and exception workflow module.



Status:



Active development.



Current capabilities:



\- DockOS route exists.

\- River route redirects to DockOS.

\- Permission handling added.

\- Access visibility logic started.



Key principles:



\- Supplier/vendor isolation.

\- Role-based access.

\- Excel upload validation before mutation.

\- Duplicate and amount mismatch handling.

\- Audit trail for operational changes.



Local route:



http://localhost:5173/dockos



\---



\### 3. Planogram Studio



Purpose:



Planogram and darkstore layout intelligence module.



Current architecture:



OPEX Control Center uses /planogram route.

Legacy PlanAI frontend currently runs separately and is shown through integration/iframe approach.



Local routes:



OPEX route:



http://localhost:5173/planogram



Legacy PlanAI frontend:



http://localhost:5174



PlanAI backend:



http://localhost:8001



Local paths:



Frontend:



C:\\Users\\ErdiAydın\\planai\\frontend



Backend:



C:\\Users\\ErdiAydın\\planai\\backend



Current status:



\- Legacy PlanAI frontend runs on 5174.

\- Backend expected on 8001.

\- Planogram UI opens.

\- Some Three.js deprecation warnings exist but are non-fatal.



Key principles:



\- Fixture-first.

\- Constraint-first.

\- Solver before visual renderer.

\- 3D must represent validated physical placement, not hide broken logic.



Future direction:



Move PlanAI frontend components into:



frontend/src/modules/planogram



Move backend engine into:



backend/app/modules/planogram



\---



\### 4. Budget Intelligence



Purpose:



Budget / OPEX finance control and intelligence module.



Status:



Module entry exists / planned.



Local route:



http://localhost:5173/budget



Key principles:



\- Expense tracking.

\- Budget variance.

\- Duplicate and mismatch control.

\- Finance-friendly review flow.



\---



\### 5. Academy



Purpose:



Training, SOP, document, video and AI-assisted learning platform.



Status:



Planned / early design.



Key principles:



\- Light theme by default.

\- Dark mode only optional.

\- Role-based learning paths.

\- RAG chatbot may be added later.

\- Answers must be grounded in accessible documents.

\- Quality must be evaluated, not guessed.



\---



\### 6. AI Insight Base



Purpose:



AI-assisted operational commentary, anomaly explanation and decision support layer.



Status:



Planned.



Key principles:



\- AI should not just generate text.

\- AI output must be traceable.

\- Langfuse-style observability.

\- Ragas-style quality evaluation.

\- Human-in-the-loop for critical decisions.



\---



\### 7. Access Control



Purpose:



User, group, module and feature permission management.



Status:



Active foundation.



Local route:



http://localhost:5173/access-control



Key principles:



\- Frontend visibility is not security.

\- Backend must enforce access.

\- Module and feature permissions should be explicit.



\## Local Services



\### OPEX frontend



Path:



C:\\Users\\ErdiAydın\\opex-control-center-scaffold\\frontend



Command:



npm run dev



Port:



5173



\---



\### PlanAI frontend



Path:



C:\\Users\\ErdiAydın\\planai\\frontend



Command:



npm run dev -- --port 5174 --strictPort



Port:



5174



\---



\### PlanAI backend



Path:



C:\\Users\\ErdiAydın\\planai\\backend



Command:



.\\.venv\\Scripts\\Activate.ps1

python -m uvicorn main:app --reload --port 8001



Port:



8001



\## Architecture Principles



AI suggests.

LangGraph manages workflow.

OR-Tools validates and optimizes.

Ragas evaluates quality.

Langfuse traces and monitors.

Humans approve critical decisions.



\## Project Rule



Do not add more features before the current module map, runbook, and roadmap are documented.



Every major module should have:



\- Purpose

\- Current status

\- Local path

\- Local route

\- Port dependency

\- Git status

\- Known issues

\- Next action

