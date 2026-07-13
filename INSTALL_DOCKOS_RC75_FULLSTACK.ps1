$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"

foreach ($Command in @("node", "npm", "python")) {
  if (!(Get-Command $Command -ErrorAction SilentlyContinue)) {
    throw "$Command bulunamadi. Node.js 22+ ve Python 3.12+ kurulu olmalidir."
  }
}

Write-Host "DockOS RC7.5 frontend bagimliliklari kuruluyor..." -ForegroundColor Cyan
Push-Location $ProjectRoot
try {
  if (Test-Path (Join-Path $ProjectRoot "package-lock.json")) { npm ci }
  else { npm install }
} finally { Pop-Location }

Write-Host "DockOS RC7.5 backend sanal ortami kuruluyor..." -ForegroundColor Cyan
Push-Location $BackendRoot
try {
  if (!(Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
  .\.venv\Scripts\python.exe -m pip install --upgrade pip
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
} finally { Pop-Location }

$EnvFile = Join-Path $ProjectRoot ".env"
if (!(Test-Path $EnvFile)) {
  Copy-Item (Join-Path $ProjectRoot ".env.example") $EnvFile
  Write-Warning ".env olusturuldu. Canli kullanimdan once CHANGE_ME, SMTP ve alici alanlarini doldurun."
}

Write-Host "DockOS RC7.5 Full Stack kurulumu tamamlandi." -ForegroundColor Green
Write-Host "Baslatmak icin: .\START_DOCKOS_RC75_FULLSTACK.ps1" -ForegroundColor Yellow
