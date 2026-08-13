$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BackendPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Kurulum bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin. PowerShell'de .\ on eki zorunludur."
}
if (!(Test-Path (Join-Path $ProjectRoot "node_modules"))) {
  throw "Frontend bagimliliklari bulunamadi. Once .\INSTALL_DOCKOS_RC75_FULLSTACK.ps1 calistirin."
}

$BackendCommand = @"
Set-Location '$BackendRoot'
`$env:DOCKOS_ENV='development'
& '$BackendPython' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCommand
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; npm run dev -- --host 0.0.0.0"
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173/workforce"

Write-Host "OPEX Workforce yonetim paneli baslatildi." -ForegroundColor Green
Write-Host "Yonetim: http://localhost:5173/workforce" -ForegroundColor Cyan
Write-Host "Picker:  http://localhost:5173/workforce/app" -ForegroundColor Cyan
Write-Host "API:     http://localhost:8000/api/workforce/health" -ForegroundColor Cyan
