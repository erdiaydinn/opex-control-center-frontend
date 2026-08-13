$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ProjectRoot ".env"
$ArtifactRoot = Join-Path $ProjectRoot "test-artifacts"

function Read-DotEnv([string]$Path) {
  $values = @{}
  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if (!$trimmed -or $trimmed.StartsWith("#") -or !$trimmed.Contains("=")) { continue }
    $parts = $trimmed.Split(@("="), 2, [System.StringSplitOptions]::None)
    $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
  }
  return $values
}

function Assert-LastExit([string]$Message) {
  if ($LASTEXITCODE -ne 0) { throw "$Message (exit: $LASTEXITCODE)" }
}

function Test-Http([string]$Name, [string]$Url, [hashtable]$Headers = @{}) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15 -Headers $Headers
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) { throw "HTTP $($response.StatusCode)" }
    Write-Host "[OK] $Name - HTTP $($response.StatusCode)" -ForegroundColor Green
    return $response
  } catch {
    throw "$Name basarisiz: $($_.Exception.Message)"
  }
}

if (!(Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop bulunamadi." }
if (!(Test-Path $EnvFile)) { throw ".env bulunamadi. Once .\INSTALL_OPEX_WORKFORCE_LOCAL_PILOT_V13_1.ps1 calistirin." }

$envValues = Read-DotEnv $EnvFile
if ($envValues["VITE_LOCAL_PILOT_MODE"] -ne "true") {
  throw "Bu test hazirligi Yerel Pilot icindir. VITE_LOCAL_PILOT_MODE=true degil."
}

New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
Push-Location $ProjectRoot
try {
  Write-Host "`n1/6 Docker servisleri" -ForegroundColor Cyan
  docker compose ps
  Assert-LastExit "docker compose ps calismadi"

  $running = @(docker compose ps --services --filter "status=running")
  foreach ($service in @("postgres", "backend", "backup", "frontend")) {
    if ($running -notcontains $service) { throw "$service calismiyor." }
    Write-Host "[OK] $service calisiyor." -ForegroundColor Green
  }

  Write-Host "`n2/6 PostgreSQL" -ForegroundColor Cyan
  $dbUser = if ($envValues["POSTGRES_USER"]) { $envValues["POSTGRES_USER"] } else { "opex" }
  $dbName = if ($envValues["POSTGRES_DB"]) { $envValues["POSTGRES_DB"] } else { "opex" }
  docker compose exec -T postgres pg_isready -U $dbUser -d $dbName
  Assert-LastExit "PostgreSQL hazir degil"
  Write-Host "[OK] PostgreSQL baglanti testi." -ForegroundColor Green

  Write-Host "`n3/6 Test oncesi yedek" -ForegroundColor Cyan
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $backupName = "opex_before_test_$stamp.dump"
  docker compose exec -T postgres pg_dump -U $dbUser -d $dbName --format=custom --compress=9 --no-owner --no-acl --file="/tmp/$backupName"
  Assert-LastExit "Test oncesi PostgreSQL yedegi olusturulamadi"
  $backupPath = Join-Path $ArtifactRoot $backupName
  docker compose cp "postgres:/tmp/$backupName" $backupPath
  Assert-LastExit "PostgreSQL yedegi bilgisayara kopyalanamadi"
  $hash = (Get-FileHash -Algorithm SHA256 $backupPath).Hash.ToLowerInvariant()
  Set-Content -Path "$backupPath.sha256" -Value "$hash  $backupName" -Encoding ASCII
  Write-Host "[OK] Yedek: $backupPath" -ForegroundColor Green

  Write-Host "`n4/6 API ve frontend" -ForegroundColor Cyan
  Test-Http "Backend health" "http://127.0.0.1:8000/api/workforce/health" | Out-Null
  Test-Http "Frontend" "http://127.0.0.1:8080/workforce" | Out-Null
  Test-Http "Nginx API proxy" "http://127.0.0.1:8080/api/workforce/health" | Out-Null
  $headers = @{ "X-Opex-User" = "erdi.aydin@yemeksepeti.com"; "X-Opex-Role" = "super_admin" }
  $bootstrap = Test-Http "Admin bootstrap/yetki" "http://127.0.0.1:8080/api/workforce/admin/bootstrap" $headers
  $payload = $bootstrap.Content | ConvertFrom-Json
  Write-Host "[OK] Personel: $(@($payload.people).Count), Depo: $(@($payload.warehouses).Count), Vardiya: $(@($payload.shifts).Count)" -ForegroundColor Green

  Write-Host "`n5/6 Telefon erisimi" -ForegroundColor Cyan
  try {
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" -and $_.AddressState -eq "Preferred" } | Select-Object -ExpandProperty IPAddress -Unique)
    if ($ips.Count -eq 0) { throw "LAN IP bulunamadi" }
    foreach ($ip in $ips) { Write-Host "Telefon tarayici testi: http://$ip`:8080/workforce/app" -ForegroundColor Yellow }
  } catch {
    Write-Warning "LAN IP otomatik bulunamadi. ipconfig komutundaki IPv4 adresini kullanin."
  }
  Write-Warning "LAN uzerindeki HTTP testi native/PWA, guvenilir GPS veya push testi degildir."

  Write-Host "`n6/6 Sonuc" -ForegroundColor Cyan
  Write-Host "TESTE HAZIR. Kabul listesi: docs\TEST_KABUL_LISTESI_V13_2.md" -ForegroundColor Green
  Write-Host "Hata olursa: .\COLLECT_OPEX_TEST_DIAGNOSTICS_V13_2.ps1" -ForegroundColor Yellow
} finally {
  Pop-Location
}
