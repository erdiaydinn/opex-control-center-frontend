$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BackendPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Backend sanal ortami bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}
if (!(Test-Path (Join-Path $ProjectRoot "node_modules"))) {
  throw "Frontend bagimliliklari bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}

$DataRoot = Join-Path $BackendRoot "data"
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null

$BackendCommand = @"
Set-Location '$BackendRoot'
`$env:DOCKOS_ENV='development'
`$env:DOCKOS_PO_SOURCE='LOCAL'
`$env:DOCKOS_STATE_FILE='$DataRoot\dockos_state.json'
`$env:DOCKOS_BACKUP_DIR='$DataRoot\backups'
`$env:DOCKOS_SINGLE_WORKER='true'
`$env:DOCKOS_NOTIFICATION_AUTOMATION='true'
& '$BackendPython' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCommand
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; npm run dev -- --host 0.0.0.0"
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173/dockos"

Write-Host "DockOS RC7.5 backend ve frontend baslatildi." -ForegroundColor Green
Write-Host "Arayuz: http://localhost:5173/dockos" -ForegroundColor Cyan
Write-Host "API:    http://localhost:8000/api/dockos/health" -ForegroundColor Cyan
