\# OPEX Local Runbook



This document explains how to run the OPEX Control Center ecosystem locally.



\## Local Service Map



OPEX frontend:



Path:

C:\\Users\\ErdiAydın\\opex-control-center-scaffold\\frontend



Port:

5173



URL:

http://localhost:5173



\---



PlanAI / Planogram frontend:



Path:

C:\\Users\\ErdiAydın\\planai\\frontend



Port:

5174



URL:

http://localhost:5174



\---



PlanAI / Planogram backend:



Path:

C:\\Users\\ErdiAydın\\planai\\backend



Port:

8001



URL:

http://127.0.0.1:8001



\---



Possible OPEX backend:



Port:

8000



Status:

Reserved / to be clarified later.



\## Required Services for Planogram



For OPEX Planogram Studio to work locally, these services must be running at the same time:



1\. OPEX frontend on port 5173

2\. PlanAI frontend on port 5174

3\. PlanAI backend on port 8001



Expected local route:



http://localhost:5173/planogram



Legacy PlanAI direct route:



http://localhost:5174



\## Terminal 1 - OPEX Frontend



Open PowerShell:



cd "C:\\Users\\ErdiAydın\\opex-control-center-scaffold\\frontend"



git checkout feature/opex-command-center-v2



npm run dev



Expected output:



Local: http://localhost:5173/



\## Terminal 2 - PlanAI Backend



Open a new PowerShell:



cd "C:\\Users\\ErdiAydın\\planai\\backend"



.\\.venv\\Scripts\\Activate.ps1



python -m uvicorn main:app --reload --port 8001



Expected output:



Uvicorn running on http://127.0.0.1:8001



If virtual environment activation fails, use:



Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass



Then run again:



.\\.venv\\Scripts\\Activate.ps1



\## Terminal 3 - PlanAI Frontend



Open a new PowerShell:



cd "C:\\Users\\ErdiAydın\\planai\\frontend"



npm run dev -- --port 5174 --strictPort



Expected output:



Local: http://localhost:5174/



Important:



Use --strictPort so Vite does not silently move to 5175 or 5176.



If PlanAI frontend starts on 5175 or 5176, OPEX /planogram may not work because the integration expects 5174.



\## Quick Test URLs



After starting all services, test these URLs:



OPEX home:



http://localhost:5173/



DockOS:



http://localhost:5173/dockos



Access Control:



http://localhost:5173/access-control



River redirect:



http://localhost:5173/river



Budget:



http://localhost:5173/budget



Planogram through OPEX:



http://localhost:5173/planogram



PlanAI direct:



http://localhost:5174



\## Port Cleanup



If port 5174 is already in use:



netstat -ano | findstr :5174



Find the PID at the end of the LISTENING row.



Then stop it:



Stop-Process -Id PID\_HERE -Force



If port 5175 is also occupied:



netstat -ano | findstr :5175



Stop it:



Stop-Process -Id PID\_HERE -Force



Then start PlanAI frontend again:



cd "C:\\Users\\ErdiAydın\\planai\\frontend"



npm run dev -- --port 5174 --strictPort



\## Backend Port Notes



Planogram frontend currently calls backend APIs on port 8001.



Example console error:



GET http://127.0.0.1:8001/bootstrap/ANKA net::ERR\_CONNECTION\_REFUSED



Meaning:



PlanAI frontend is running, but PlanAI backend is not running on 8001.



Fix:



cd "C:\\Users\\ErdiAydın\\planai\\backend"



.\\.venv\\Scripts\\Activate.ps1



python -m uvicorn main:app --reload --port 8001



\## Common Console Warnings



Three.js warnings may appear:



THREE.Clock has been deprecated.



THREE.WebGLShadowMap PCFSoftShadowMap has been deprecated.



These warnings are currently non-fatal.



They indicate that the 3D layer should eventually be modernized, but they do not necessarily break the app.



\## Build Validation



Before committing frontend changes:



cd "C:\\Users\\ErdiAydın\\opex-control-center-scaffold\\frontend"



npm run build



Successful output should include:



built in ...



React Router or Framer Motion use-client warnings may appear. They are non-fatal unless build fails.



\## Git Workflow



Active development branch:



feature/opex-command-center-v2



Stable branch:



main



Normal development flow:



git checkout feature/opex-command-center-v2



git status



npm run build



git add .



git commit -m "type: clear message"



git push



When stable, merge feature branch into main:



git checkout main



git pull



git merge --ff-only feature/opex-command-center-v2



git push



git checkout feature/opex-command-center-v2



\## Shutdown



To stop any running dev server:



Press Ctrl + C in the related PowerShell window.



If asked to terminate batch job, type:



Y



\## Current Known Local Architecture



OPEX Control Center remains the umbrella portal.



Planogram Studio is still served through legacy PlanAI frontend.



Current bridge:



OPEX frontend:

http://localhost:5173



Legacy PlanAI frontend:

http://localhost:5174



PlanAI backend:

http://127.0.0.1:8001



Future target:



Move PlanAI frontend components into:



frontend/src/modules/planogram



Move PlanAI backend engine into:



backend/app/modules/planogram

