$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BackendPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Kurulum bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}
if (!(Test-Path (Join-Path $ProjectRoot "node_modules"))) {
  throw "Frontend bagimliliklari bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}

$BackendCommand = @"
Set-Location '$BackendRoot'
`$env:DOCKOS_ENV='development'
`$env:OPEX_ALLOW_LEGACY_HEADERS='true'
& '$BackendPython' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCommand
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; `$env:VITE_INVENTORY_API_REQUIRED='false'; npm run dev -- --host 0.0.0.0"
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173/inventory"

Write-Host "OPEX Inventory V20 baslatildi." -ForegroundColor Green
Write-Host "Inventory: http://localhost:5173/inventory" -ForegroundColor Cyan
Write-Host "API:       http://localhost:8000/api/inventory/health" -ForegroundColor Cyan
