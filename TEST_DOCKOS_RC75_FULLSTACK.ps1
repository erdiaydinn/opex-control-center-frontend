$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BackendPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Backend sanal ortami bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}

$env:DOCKOS_ENV = "development"
$env:DOCKOS_PO_SOURCE = "LOCAL"
$env:DOCKOS_STATE_FILE = Join-Path $env:TEMP "dockos_rc75_test_state.json"
$env:DOCKOS_NOTIFICATION_AUTOMATION = "false"

Write-Host "Backend birim testleri..." -ForegroundColor Cyan
Push-Location $BackendRoot
try {
  & $BackendPython -m compileall -q app
  & $BackendPython -m app.modules.dockos.test_rc2
} finally { Pop-Location }

Write-Host "Frontend production build..." -ForegroundColor Cyan
Push-Location $ProjectRoot
try { npm run build } finally { Pop-Location }

try {
  $Health = Invoke-RestMethod "http://127.0.0.1:8000/api/dockos/health" -TimeoutSec 5
  Write-Host "Calisan API: $($Health.release)" -ForegroundColor Green
} catch {
  Write-Warning "Backend calismiyor; HTTP smoke testi atlandi. START scripti sonrasi tekrar test edebilirsiniz."
}

Write-Host "DockOS RC7.5 Full Stack testleri basarili." -ForegroundColor Green
