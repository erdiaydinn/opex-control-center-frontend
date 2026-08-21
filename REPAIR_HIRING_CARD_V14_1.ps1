$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Assert-LastExitCode([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step basarisiz oldu (exit code: $LASTEXITCODE)." }
}

Push-Location $ProjectRoot
try {
  if (!(Select-String -Path ".\src\modules\control-center\commandCenterModules.js" -Pattern 'title: "Hiring Control"' -Quiet)) {
    throw "Bu klasorde Hiring Control kaynak kodu yok. V14.1 ZIP'ini yeniden indirin."
  }

  docker info | Out-Null
  Assert-LastExitCode "Docker Desktop baglantisi"

  $envFile = Join-Path $ProjectRoot ".env"
  $prepareInstaller = Join-Path $ProjectRoot "INSTALL_OPEX_WORKFORCE_LOCAL_PILOT_V13_1.ps1"
  $databaseUrlReady = $false
  if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    $databaseUrlReady = $envContent -match "(?m)^DATABASE_URL=postgresql://.+$"
  }
  if (!$databaseUrlReady) {
    if (!(Test-Path $prepareInstaller)) {
      throw "DATABASE_URL eksik ve .env hazirlama scripti bulunamadi. ZIP'i eksiksiz cikartin."
    }
    Write-Host ".env veya DATABASE_URL eksik; yerel pilot ayarlari hazirlaniyor..." -ForegroundColor Yellow
    & $prepareInstaller -PrepareOnly
    if (!(Test-Path $envFile)) { throw ".env olusturulamadi." }
    $envContent = Get-Content $envFile -Raw
    if ($envContent -notmatch "(?m)^DATABASE_URL=postgresql://.+$") {
      throw "DATABASE_URL .env icinde olusturulamadi."
    }
  }

  Write-Host "Eski frontend/backend image onbellegi atlanarak yenileniyor..." -ForegroundColor Cyan
  docker compose build --no-cache backend frontend
  Assert-LastExitCode "Image derlemesi"
  docker compose up -d --force-recreate postgres backend backup frontend
  Assert-LastExitCode "Container yenileme"

  $ready = $false
  for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
      $health = Invoke-RestMethod -Uri "http://localhost:8000/api/recruitment/health" -TimeoutSec 3
      if ($health.status -eq "ok") { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
  }
  if (!$ready) { throw "Recruitment API hazir olmadi. 'docker compose logs backend' komutunu calistirin." }

  docker compose exec -T frontend sh -c "grep -R -q 'Hiring Control' /usr/share/nginx/html/assets"
  Assert-LastExitCode "Frontend Hiring karti dogrulamasi"
} finally {
  Pop-Location
}

Write-Host "Hiring Control karti container icinde dogrulandi." -ForegroundColor Green
Write-Host "Ctrl+F5 yapin veya dogrudan http://localhost:8080/recruitment adresini acin." -ForegroundColor Yellow
