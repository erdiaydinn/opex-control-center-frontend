$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BackendPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Backend sanal ortami bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}

Write-Host "Workforce backend testleri..." -ForegroundColor Cyan
Push-Location $ProjectRoot
try {
  & $BackendPython -m compileall -q backend/app
  & $BackendPython -m unittest backend.app.modules.workforce.test_workforce -v
  npm run build
} finally { Pop-Location }

try {
  $Health = Invoke-RestMethod "http://127.0.0.1:8000/api/workforce/health" -TimeoutSec 5
  Write-Host "Calisan API: $($Health.module)" -ForegroundColor Green
} catch {
  Write-Warning "Backend calismiyor; HTTP smoke testi atlandi. START_OPEX_WORKFORCE.ps1 sonrasi tekrar deneyin."
}

Write-Host "OPEX Workforce testleri basarili." -ForegroundColor Green
