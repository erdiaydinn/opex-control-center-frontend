$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$baseInstaller = Join-Path $ProjectRoot "INSTALL_OPEX_WORKFORCE_LOCAL_PILOT_V13_1.ps1"

function Assert-LastExitCode([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step basarisiz oldu (exit code: $LASTEXITCODE). Eski container calismaya devam ediyor olabilir."
  }
}

if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker Desktop bulunamadi. Docker Desktop'i acip tekrar deneyin."
}

docker info | Out-Null
Assert-LastExitCode "Docker Desktop baglantisi"
docker compose version | Out-Null
Assert-LastExitCode "Docker Compose kontrolu"

if (!(Test-Path $baseInstaller)) {
  throw "Ana yerel pilot kurucusu bulunamadi. ZIP dosyasini eksiksiz cikartin."
}

Push-Location $ProjectRoot
try {
  Write-Host "1/4 Yerel pilot .env ayarlari hazirlaniyor..." -ForegroundColor Cyan
  & $baseInstaller -PrepareOnly

  Write-Host "2/4 Hiring backend ve frontend onbelleksiz derleniyor..." -ForegroundColor Cyan
  docker compose build --no-cache backend frontend
  Assert-LastExitCode "Hiring image derlemesi"

  Write-Host "3/4 Container'lar yeni image ile zorla yenileniyor..." -ForegroundColor Cyan
  docker compose up -d --force-recreate postgres backend backup frontend
  Assert-LastExitCode "Hiring container kurulumu"

  Write-Host "4/4 Recruitment API ve frontend paketi dogrulaniyor..." -ForegroundColor Cyan
  $ready = $false
  for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
      $health = Invoke-RestMethod -Uri "http://localhost:8000/api/recruitment/health" -TimeoutSec 3
      if ($health.status -eq "ok") { $ready = $true; break }
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  if (!$ready) {
    docker compose logs --tail 120 backend
    throw "Recruitment API 60 saniye icinde hazir olmadi. Yukaridaki backend logunu kontrol edin."
  }

  docker compose exec -T frontend sh -c "grep -R -q 'Hiring Control' /usr/share/nginx/html/assets"
  Assert-LastExitCode "Frontend Hiring Control dogrulamasi"

  docker compose ps
  Assert-LastExitCode "Container durum kontrolu"
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "OPEX Hiring Control V14.1 hazir." -ForegroundColor Green
Write-Host "Control Center: http://localhost:8080" -ForegroundColor Green
Write-Host "Hiring Control: http://localhost:8080/recruitment" -ForegroundColor Green
Write-Host "Tarayicida Ctrl+F5 ile tam yenileme yapin." -ForegroundColor Yellow
